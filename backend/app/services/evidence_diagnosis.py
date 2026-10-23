"""Scope, freeze and validate evidence before it can affect a learning diagnosis."""

import hashlib
import json
import time
from copy import deepcopy
from datetime import timedelta, timezone

import httpx
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.agents.diagnosis_guardrails import contains_prompt_leak, is_instruction_attack
from app.agents.evidence_diagnosis import PROMPT, PROMPT_VERSION
from app.core.errors import fail
from app.models import KnowledgePoint, LearningEvent, ModelTrace
from app.models.diagnosis_report import DiagnosisReport
from app.models.legacy import now
from app.schemas.diagnosis_report import PointDiagnosis, ReportFeedback
from app.services.c_model_gateway import ModelCallError, complete_json
from app.services.diagnosis_presentation import PRESENTATION_VERSION, render_point, verified_behavior
from app.services.prerequisites import lock_course
from app.services.profile import apply_report


def input_fingerprint(settings, snapshot):
    # Moving window endpoints alone are not new evidence. Contents, scope and
    # inference configuration must all match; never include credentials.
    data = {
        "version": "evidence-reuse-v1",
        "prompt": PROMPT_VERSION,
        "presentation": PRESENTATION_VERSION,
        "backend": settings.c_llm_backend,
        "model": settings.c_llm_model or settings.llm_model,
        "endpoint": settings.llm_base_url if settings.c_llm_backend == "api" else "local-codex",
        "student": snapshot["student_id"], "course": snapshot["course_id"],
        "days": snapshot["days"],
        "points": sorted(snapshot["points"], key=lambda p: p["knowledge_point_id"]),
        "candidate_limit_reached": snapshot.get("candidate_limit_reached", False),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def reusable_result(db, row, fingerprint):
    if not fingerprint:
        return None
    prior = db.scalar(
        select(DiagnosisReport).join(ModelTrace, ModelTrace.trace_id == DiagnosisReport.trace_id)
        .where(DiagnosisReport.course_id == row.course_id,
               DiagnosisReport.student_id == row.student_id,
               DiagnosisReport.id != row.id,
               DiagnosisReport.status.in_(("supported", "insufficient")),
               ModelTrace.details["input_fingerprint"].as_string() == fingerprint)
        .order_by(DiagnosisReport.created_at, DiagnosisReport.id).limit(1)
    )
    if prior is None or not prior.output:
        return None
    output = deepcopy(prior.output)
    output["model_called"] = False
    output["reuse"] = {"report_id": prior.id, "reason": "same_evidence_and_configuration"}
    return output


def utc(value):
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)


def facts(events):
    graded = [e for e in events if e["source"] == "assessment" and type(e.get("correct")) is bool]
    wrong = sum(not e["correct"] for e in graded)
    observations = [e for e in events if e["source"] == "behavior"]
    return {
        "graded_count": len(graded),
        "wrong_count": wrong,
        "accuracy": (len(graded) - wrong) / len(graded) if graded else None,
        "latest_correct": graded[-1]["correct"] if graded else None,
        "dialogue_count": sum(e["source"] in ("dialogue", "practice") for e in events),
        "behavior_available": bool(observations),
        "behavior_observations": [e["measurement"] for e in observations],
        "prerequisite_errors": [
            e["event_id"] for e in graded if e.get("prerequisite_check") and not e["correct"]
        ],
    }


def safe_event(event, kp):
    obj, result, context = event.object, event.result, event.context
    kind = obj.get("type")
    source = {
        "assessment": "assessment",
        "practice": "practice",
        "learning_5e": "dialogue",
        "question": "dialogue",
    }.get(kind)
    item = {"event_id": event.event_id, "timestamp": utc(event.timestamp).isoformat()}
    if source:
        if kind == "question":
            # Only the learner's question is evidence, never the model's answer.
            answer = result.get("question", "")
        else:
            answer = result.get("answer", "")
        item.update(
            source=source,
            question=str(obj.get("question", ""))[:1000],
            answer=str(answer)[:1000],
            stage=obj.get("stage"),
            correct=result.get("correct") if kind == "assessment" else None,
            prerequisite_check=(obj.get("assessment_context", {}).get("prerequisite_for") == kp.id),
        )
        return item
    # Future resource producers must write verified server measurements under this contract.
    # No browser endpoint in this module accepts or manufactures learning behavior.
    if (
        kind != "resource"
        or context.get("source") != "resource_tracker"
        or context.get("measurement") != "server"
    ):
        return None
    measurement = {
        key: result.get(key)
        for key in (
            "effective_seconds",
            "coverage",
            "resource_available",
            "study_visits",
            "observation_complete",
        )
    }
    if (
        type(measurement["effective_seconds"]) not in (int, float)
        or not 0 <= measurement["effective_seconds"] <= 90 * 86400
        or type(measurement["coverage"]) not in (int, float)
        or not 0 <= measurement["coverage"] <= 1
        or type(measurement["study_visits"]) is not int
        or measurement["study_visits"] < 0
        or type(measurement["resource_available"]) is not bool
        or type(measurement["observation_complete"]) is not bool
    ):
        return None
    return {**item, "source": "behavior", "measurement": measurement}


def collect_snapshot(db, course_id, student_id, body):
    cutoff = now()
    start = cutoff - timedelta(days=body.days)
    points = [db.get(KnowledgePoint, key) for key in body.knowledge_point_ids]
    if any(p is None or p.course_id != course_id for p in points):
        fail(422, "KNOWLEDGE_POINT_MISMATCH", "知识点必须属于本课程")
    candidates = db.scalars(
        select(LearningEvent)
        .where(
            LearningEvent.actor == student_id,
            LearningEvent.context["course"].as_string() == course_id,
            LearningEvent.timestamp >= start,
            LearningEvent.timestamp <= cutoff,
        )
        .order_by(LearningEvent.timestamp.desc(), LearningEvent.event_id.desc())
        .limit(2000)
    ).all()
    result = []
    for point in points:
        events, omitted = [], 0
        for event in candidates:
            # Explicitly exclude synthetic and unclassified legacy data.
            if event.context.get("synthetic") is not False:
                continue
            keys = event.object.get("kp", [])
            if not isinstance(keys, list) or not {point.id, point.code}.intersection(keys):
                continue
            item = safe_event(event, point)
            if item:
                if len(events) < 30:
                    events.append(item)
                else:
                    omitted += 1
        events.reverse()
        result.append(
            {
                "knowledge_point_id": point.id,
                "code": point.code,
                "name": point.name,
                "definition": point.definition,
                "events": events,
                "baseline": facts(events),
                "omitted_older_events": omitted,
            }
        )
    return {
        "student_id": student_id,
        "course_id": course_id,
        "days": body.days,
        "from": start.isoformat(),
        "cutoff": cutoff.isoformat(),
        "points": result,
        "candidate_limit_reached": len(candidates) == 2000,
        "behavior_collection": "尚未接入播放/阅读采集；仅接受已存在的服务端测量事件。",
    }


def out(row):
    result = {
        key: getattr(row, key)
        for key in (
            "id",
            "course_id",
            "student_id",
            "status",
            "snapshot",
            "output",
            "trace_id",
            "error_code",
            "error_message",
            "created_at",
        )
    }
    result["created_at"] = utc(row.created_at)
    return result


def same_request(row, body):
    return (
        row.snapshot["days"] == body.days
        and [p["knowledge_point_id"] for p in row.snapshot["points"]] == body.knowledge_point_ids
    )


def create_report(sessions, settings, course_id, student_id, body):
    try:
        with sessions.begin() as db:
            existing = db.scalar(
                select(DiagnosisReport).where(
                    DiagnosisReport.course_id == course_id,
                    DiagnosisReport.student_id == student_id,
                    DiagnosisReport.request_id == str(body.request_id),
                )
            )
            if existing:
                if not same_request(existing, body):
                    fail(409, "REQUEST_CONFLICT", "请求编号已用于不同诊断范围")
                return out(existing), False
            snapshot = collect_snapshot(db, course_id, student_id, body)
            trace = ModelTrace(
                source="live",
                feature="learning.diagnosis",
                model=settings.c_llm_model or settings.llm_model,
                prompt_version=PROMPT_VERSION,
                input_summary={
                    "student_id": student_id,
                    "course_id": course_id,
                    "cutoff": snapshot["cutoff"],
                    "event_count": sum(len(p["events"]) for p in snapshot["points"]),
                },
                details={"backend": settings.c_llm_backend,
                         "input_fingerprint": input_fingerprint(settings, snapshot)},
            )
            db.add(trace)
            db.flush()
            row = DiagnosisReport(
                course_id=course_id,
                student_id=student_id,
                request_id=str(body.request_id),
                snapshot=snapshot,
                trace_id=trace.trace_id,
            )
            db.add(row)
            db.flush()
            result = out(row)
        return result, True
    except IntegrityError:
        with sessions() as db:
            existing = db.scalar(
                select(DiagnosisReport).where(
                    DiagnosisReport.course_id == course_id,
                    DiagnosisReport.student_id == student_id,
                    DiagnosisReport.request_id == str(body.request_id),
                )
            )
            if existing and same_request(existing, body):
                return out(existing), False
        raise


def insufficient(point, reason):
    return PointDiagnosis(
        knowledge_point_id=point["knowledge_point_id"],
        status="insufficient",
        mastery=None,
        confidence=0,
        problem_type="insufficient_evidence",
        explanation=reason,
        recommendation="补充该知识点的作答和判断依据后再分析。",
        followup_question="你会用什么例子说明自己的理解？",
        evidence_event_ids=[e["event_id"] for e in point["events"]],
        citations=[],
    )


def validate_feedback(snapshot, feedback):
    actions = []
    by_id = {p["knowledge_point_id"]: p for p in snapshot["points"]}
    ids = [p.knowledge_point_id for p in feedback.points]
    if len(set(ids)) != len(ids) or set(ids) != set(by_id):
        raise ModelCallError("INVALID_KNOWLEDGE_POINT", "模型返回的知识点范围不匹配，结果未采纳。")
    if contains_prompt_leak(json.dumps(feedback.model_dump(), ensure_ascii=False), PROMPT):
        raise ModelCallError("PROMPT_LEAK", "模型输出包含系统指令，结果未采纳。")
    for index, point in enumerate(feedback.points):
        original = by_id[point.knowledge_point_id]
        events = original["events"]
        allowed = {e["event_id"] for e in events}
        if not set(point.evidence_event_ids) <= allowed or (
            point.status == "supported" and not point.evidence_event_ids
        ):
            raise ModelCallError("INVALID_EVIDENCE", "模型引用了不属于本次知识点快照的证据。")
        if point.status != "supported":
            continue
        stats = facts(events)
        cited = [e for e in events if e["event_id"] in point.evidence_event_ids]
        if not any(e["source"] in ("assessment", "practice", "dialogue") for e in cited):
            raise ModelCallError("INVALID_EVIDENCE", "掌握度判断必须引用学生答题或对话证据。")
        unsupported = None
        if point.problem_type == "repeated_error" and (
            sum(e["source"] == "assessment" and e.get("correct") is False for e in cited) < 3
            or stats["latest_correct"] is True
        ):
            unsupported = ("UNSUPPORTED_PATTERN", "反复错误判断缺少足够且未纠正的客观错答证据。")
        if point.problem_type == "prerequisite_gap" and not set(stats["prerequisite_errors"]).intersection(
            point.evidence_event_ids
        ):
            unsupported = ("UNSUPPORTED_PATTERN", "前置知识不足判断缺少明确的前置检查证据。")
        latest_behavior = next((e for e in reversed(events) if e["source"] == "behavior"), None)
        measured = (
            [latest_behavior["measurement"]]
            if latest_behavior and latest_behavior["event_id"] in point.evidence_event_ids
            else []
        )
        if point.problem_type in ("low_engagement", "practice_only") and not measured:
            unsupported = ("UNSUPPORTED_BEHAVIOR", "没有服务端行为测量，不能推断投入不足或只刷题。")
        if point.problem_type == "low_engagement" and not any(
            m["resource_available"]
            and m["observation_complete"]
            and m["coverage"] <= 0.2
            and m["effective_seconds"] < 120
            for m in measured
        ):
            unsupported = ("UNSUPPORTED_BEHAVIOR", "行为测量未达到低投入观察条件，结果未采纳。")
        if point.problem_type == "practice_only" and not (
            stats["graded_count"] >= 3
            and any(
                m["resource_available"] and m["observation_complete"] and m["study_visits"] == 0
                for m in measured
            )
        ):
            unsupported = ("UNSUPPORTED_BEHAVIOR", "只刷题判断缺少完整观察窗口和资源可用性证据。")
        if unsupported:
            actions.append(
                {
                    "knowledge_point_id": point.knowledge_point_id,
                    "code": unsupported[0],
                    "rejected_problem_type": point.problem_type,
                    "action": "downgrade_to_insufficient",
                }
            )
            feedback.points[index] = insufficient(original, unsupported[1])
    return feedback, actions


def infer_snapshot(settings, snapshot):
    local, eligible, excluded = [], [], []
    actions = []
    clean_points, drafts = {}, []
    for point in snapshot["points"]:
        clean = [e for e in point["events"] if not is_instruction_attack(str(e.get("answer", "")))]
        excluded.extend(e["event_id"] for e in point["events"] if e not in clean)
        selected = {**point, "events": clean, "baseline": facts(clean)}
        clean_points[point["knowledge_point_id"]] = selected
        if len(clean) < 2:
            local.append(insufficient(selected, "可用证据不足两条，暂不推断掌握度。"))
        else:
            stats = selected["baseline"]
            selected["trusted_summary"] = {
                "graded_count": stats["graded_count"],
                "correct_count": stats["graded_count"] - stats["wrong_count"],
                "wrong_count": stats["wrong_count"],
                "verified_behavior": verified_behavior(clean, stats),
                "latest_dialogue_event_id": next(
                    (e["event_id"] for e in reversed(clean) if e["source"] in ("dialogue", "practice")), None
                ),
            }
            eligible.append(selected)
    usage, actual_model = None, settings.c_llm_model or settings.llm_model
    if eligible:
        data = {**snapshot, "points": eligible}
        reply = complete_json(settings, PROMPT, data, ReportFeedback.model_json_schema())
        try:
            raw = json.loads(reply.text)
        except (ValueError, TypeError):
            raise ModelCallError(
                "INVALID_MODEL_RESPONSE",
                "模型未返回有效 JSON，本次结果未采纳。",
                {"phase": "json_decode"},
            ) from None
        if contains_prompt_leak(json.dumps(raw, ensure_ascii=False), PROMPT):
            raise ModelCallError("PROMPT_LEAK", "模型输出包含系统指令，结果未采纳。")
        original_draft = deepcopy(raw)
        normalized = []
        if isinstance(raw, dict) and isinstance(raw.get("points"), list):
            for item in raw["points"]:
                if not isinstance(item, dict):
                    continue
                if (
                    item.get("status") == "insufficient"
                    or item.get("problem_type") == "insufficient_evidence"
                ):
                    if (
                        item.get("status") != "insufficient"
                        or item.get("mastery") is not None
                        or item.get("problem_type") != "insufficient_evidence"
                    ):
                        normalized.append(
                            {
                                "knowledge_point_id": item.get("knowledge_point_id"),
                                "code": "INCONSISTENT_INSUFFICIENCY",
                                "action": "normalize_to_insufficient",
                                "rejected_problem_type": item.get("problem_type"),
                            }
                        )
                        item.update(
                            status="insufficient",
                            mastery=None,
                            problem_type="insufficient_evidence",
                            explanation="模型返回的证据不足状态与掌握度或类型不一致，本次按证据不足处理。",
                        )
        try:
            parsed = ReportFeedback.model_validate(raw)
        except ValidationError as exc:
            fields = {"points"} | set(PointDiagnosis.model_fields)
            issues = [
                {
                    "field": ".".join(
                        str(v) if isinstance(v, int) or v in fields else "extra_field" for v in error["loc"]
                    ),
                    "type": error["type"],
                }
                for error in exc.errors()[:8]
            ]
            raise ModelCallError(
                "INVALID_MODEL_RESPONSE",
                "模型输出字段校验失败，本次结果未采纳。",
                {"phase": "schema_validation", "issues": issues},
            ) from None
        model_result, actions = validate_feedback(data, parsed)
        actions = normalized + actions
        drafts = original_draft["points"]
        local.extend(model_result.points)
        usage, actual_model = reply.usage, reply.model
    by_id = {p.knowledge_point_id: p for p in local}
    observations, presentation_actions = [], []
    for key, point in by_id.items():
        original = clean_points[key]
        stats = original["baseline"]
        observed = verified_behavior(original["events"], stats)
        if observed:
            observations.append({"knowledge_point_id": key, **observed, "source": "server_rule"})
        higher_priority = stats["prerequisite_errors"] or (
            stats["wrong_count"] >= 3 and stats["latest_correct"] is False
        )
        if (
            observed
            and not higher_priority
            and original in eligible
            and point.problem_type
            in ("insufficient_evidence", "no_obvious_issue", "low_engagement", "practice_only")
            and point.problem_type != observed["problem_type"]
        ):
            actions.append(
                {
                    "knowledge_point_id": key,
                    "code": "VERIFIED_BEHAVIOR_CLASSIFICATION",
                    "action": "apply_verified_behavior_rule",
                    "rejected_problem_type": point.problem_type,
                    "applied_problem_type": observed["problem_type"],
                }
            )
            point = PointDiagnosis.model_validate(
                {
                    **point.model_dump(),
                    "status": "supported",
                    "problem_type": observed["problem_type"],
                    # The rule can establish behavior, never manufacture a mastery or confidence score.
                    "mastery": point.mastery if point.status == "supported" else None,
                    "confidence": None,
                    "evidence_event_ids": list(
                        dict.fromkeys(
                            [
                                *point.evidence_event_ids,
                                observed["evidence_event_id"],
                            ]
                        )
                    ),
                }
            )
        by_id[key] = render_point(point, original, stats)
        presentation_actions.append(
            {"knowledge_point_id": key, "action": "render_evidence_and_authored_task"}
        )
    result = {
        "points": [by_id[p["knowledge_point_id"]].model_dump() for p in snapshot["points"]],
        "excluded_instruction_events": excluded,
        "model_called": bool(eligible),
        "guardrail_actions": actions,
        "model_drafts": drafts,
        "observed_behaviors": observations,
        "presentation_version": PRESENTATION_VERSION,
        "presentation_actions": presentation_actions,
    }
    return result, usage, actual_model


def run_report(sessions, settings, report_id, trace_id):
    started = time.perf_counter()
    with sessions() as db:
        row = db.get(DiagnosisReport, report_id)
        if row.status != "pending" or row.trace_id != trace_id:
            return
        snapshot = row.snapshot
        fingerprint = (db.get(ModelTrace, trace_id).details or {}).get("input_fingerprint")
        reused = reusable_result(db, row, fingerprint)
    output, usage, actual_model, failure, failure_details = None, None, None, None, None
    try:
        if reused is not None:
            output = reused
        else:
            output, usage, actual_model = infer_snapshot(settings, snapshot)
    except ModelCallError as exc:
        failure = (exc.code, exc.message)
        failure_details = exc.details
    except httpx.TimeoutException:
        failure = ("MODEL_TIMEOUT", "模型超时，证据快照已保存，可以重试。")
    except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
        failure = ("INVALID_MODEL_RESPONSE", "模型请求或输出校验失败，证据快照已保存。")
    except Exception:
        failure = ("INTERNAL_DIAGNOSIS_ERROR", "诊断处理失败，请凭 trace 编号排查。")
    with sessions.begin() as db:
        # Serialize the final decision: concurrently completed identical inputs
        # keep the first accepted result, even if both started model inference.
        lock_course(db, snapshot["course_id"])
        row = db.get(DiagnosisReport, report_id)
        if row.status != "pending" or row.trace_id != trace_id:
            return
        trace = db.get(ModelTrace, trace_id)
        accepted = reusable_result(db, row, fingerprint)
        if accepted is not None:
            # Preserve the fact/usage of a concurrent model call even though
            # its estimate loses to the already accepted identical input.
            accepted["model_called"] = bool(output and output.get("model_called"))
            output, failure, failure_details = accepted, None, None
        trace.latency_ms = round((time.perf_counter() - started) * 1000)
        trace.usage = usage
        if failure:
            row.status, trace.status = "failed", "failed"
            row.error_code, row.error_message = failure
            trace.error_code = failure[0]
            if failure_details:
                trace.details = {**(trace.details or {}), "failure": failure_details}
        else:
            row.output = output
            row.status = (
                "supported" if any(p["status"] == "supported" for p in output["points"]) else "insufficient"
            )
            trace.status = "succeeded" if output["model_called"] else "insufficient"
            if output.get("reuse"):
                trace.status = "reused"
            trace.model = actual_model or "unconfigured" if output["model_called"] else "not_called"
            trace.details = {
                **(trace.details or {}),
                "excluded_instruction_events": output["excluded_instruction_events"],
                "guardrail_actions": output["guardrail_actions"],
                "presentation_version": output["presentation_version"],
                "observed_behaviors": output["observed_behaviors"],
                "reuse": output.get("reuse"),
                "inference_attempted": reused is None,
            }
            # Commit the diagnosis and its idempotent mastery projection together.
            db.flush()
            apply_report(db, row)


def retry_report(sessions, settings, report_id):
    with sessions.begin() as db:
        claimed = db.execute(
            update(DiagnosisReport)
            .where(
                DiagnosisReport.id == report_id,
                DiagnosisReport.status == "failed",
            )
            .values(status="pending", error_code=None, error_message=None)
        )
        if not claimed.rowcount:
            fail(409, "RETRY_NOT_ALLOWED", "仅失败的诊断可重试")
        row = db.get(DiagnosisReport, report_id)
        trace = ModelTrace(
            source="live",
            feature="learning.diagnosis",
            prompt_version=PROMPT_VERSION,
            model=settings.c_llm_model or settings.llm_model,
            input_summary={"report_id": report_id, "cutoff": row.snapshot["cutoff"]},
            details={"backend": settings.c_llm_backend, "retry_of": row.trace_id,
                     "input_fingerprint": input_fingerprint(settings, row.snapshot)},
        )
        db.add(trace)
        db.flush()
        row.trace_id = trace.trace_id
        return trace.trace_id


def recover_reports(db):
    db.execute(
        update(DiagnosisReport)
        .where(DiagnosisReport.status == "pending")
        .values(
            status="failed",
            error_code="PROCESS_INTERRUPTED",
            error_message="上次诊断中断，快照保留，可以重试。",
        )
    )
