"""Run 5 knowledge points x 3 scripted student types against the configured real C model.

Requires --live. Writes an isolated SQLite evaluation DB and trace-linked reports.
This checks learning workflow/model behavior, not real students' learning gains.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.agents.learning_templates import LEARNING_PROMPT_VERSION, TEMPLATES  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import ModelTrace  # noqa: E402
from app.services.seed import seed_data  # noqa: E402

ANSWERS = {
    "KP-REQ-01": [
        "我用过的选课系统可以查课程，但高峰时加载很慢，我希望它在许多人同时使用时仍能及时响应。",
        "可以导出报告描述系统提供什么功能，两秒内生成则限制这个功能在特定场景下的性能。两者的验收方式不同。",
        "功能需求规定系统做什么，例如导出选课报告；非功能需求约束运行质量，例如并发一百人时百分之九十五的请求两秒内完成。",
        "选课系统应允许学生按课程编号查询；在一百名学生并发查询时，百分之九十五的响应时间不超过两秒，这样可以测量验收。",
        "我选择B，因为它给出了百分之九十五请求和两秒的量化性能指标，A和C描述提供什么功能。",
    ],
    "KP-REQ-02": [
        "我作为学生进入选课系统，希望成功选到课程；我输入课程号并发起选课，系统反馈是否成功。",
        "学生在系统外发起选课，外部支付平台可能在系统外完成交互，它们可以是参与者；系统自身在边界内，不是自己的外部参与者。",
        "参与者是与系统交互的外部角色，可以是人或其他系统；用例描述角色为实现目标与系统发生的交互，例如学生选课。",
        "图书借阅系统中，读者是参与者，其用例为借书；图书管理员是另一参与者，其用例为登记归还并维护库存。",
        "我选择B，参与者由系统边界外的交互角色定义，不是系统内部对象，也不局限于数据库表。",
    ],
    "KP-VAL-01": [
        "我遇到过一个报表系统，按钮与计算都正常，却无法支持用户实际的统计场景，所以功能正常仍不好用。",
        "我会先假设规格本身遗漏了真实场景，一方面检查实现是否符合规格，另一方面向用户核实实际用途和需要，这两种检查对象不同。",
        "验证关注是否符合规定要求，确认关注是否满足预期用途和用户需要。例如核对报表计算规则属于验证，让用户按实际业务完成统计属于确认。",
        "选课规格测试全部通过但学生仍不能完成选课时，我先复现真实选课场景，核实并发、时间冲突等实际需要是否遗漏；同时保留规格符合性检查。",
        "我选择B。符合设计规格只能支持验证结论，还要确认是否满足预期用途和用户实际需要，规格本身可能不完整。",
    ],
    "KP-TEST-01": [
        "年龄框不能只测试正常值，因为小于下限、超过上限或空输入可能走不同逻辑，甚至造成错误注册。",
        "十八到六十岁是有效类，低于十八和高于六十分别是无效类；我选择三十、十七、六十一来检查各组预期接受或拒绝的行为。",
        "等价类划分按预期处理行为把输入分组；有效类应接受，无效类应拒绝，每类选代表值，避免只选多个正常值却遗漏异常。",
        "商品数量只接受一到一百时，我把一到一百划为有效类，零及以下和一百零一及以上作为无效类，分别选择五十、零、一百零一。",
        "我选择C，十七对应低于下限的无效类，三十对应有效类，六十一对应高于上限的无效类，覆盖三种预期行为。",
    ],
    "KP-BOUND-01": [
        "购物数量在最小值或最大值附近出错，可能拒绝正常订单或者接受非法数量，因此我担心边界判断条件写错。",
        "对于整数一到一百，我优先考虑零、一、二、九十九、一百、一百零一，覆盖边界、紧邻内侧与外侧，并检查接受或拒绝行为。",
        "边界值分析重点测试输入边界附近容易出错的位置；等价类先确定各输入类别，两种方法结合能覆盖类别及边界风险。",
        "密码长度允许八到二十字符时，我测试七、八、九、十九、二十、二十一；七和二十一应拒绝，其余长度应接受，以检查上下界及邻近值。",
        "我选择B，其中零和一百零一覆盖紧邻外侧无效值，一和一百覆盖两个有效边界；比只选中间正常值更能发现边界判断错误。",
    ],
}
CONFUSIONS = {
    "KP-REQ-01": "导出报告和两秒内生成都是同一种功能需求，不需要分别验收，系统能运行就足够了。",
    "KP-REQ-02": "选课系统自己和系统内部数据库表都是它自己的外部参与者，学生不是参与者。",
    "KP-VAL-01": "验证检查用户是否满意，确认检查代码是否符合设计规格，符合规格就一定满足实际需要。",
    "KP-TEST-01": "只选二十、三十、四十这些正常年龄即可覆盖全部等价类，不必检查小于十八或大于六十。",
    "KP-BOUND-01": "一到一百只测二十、五十和八十即可发现所有边界错误，边界值和紧邻外侧的值没有区别。",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--student-kinds",
        nargs="+",
        choices=["ready", "confused", "insufficient"],
        default=["ready", "confused", "insufficient"],
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".local/c-live-learning.json"
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("真实评测需显式添加 --live，未执行模型调用。")
    settings = Settings(
        database_url=f"sqlite:///{(ROOT / '.local/c-live-learning.db').as_posix()}",
        allowed_origins=["http://testserver"],
        enable_dev_routes=False,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    password = "C-evaluation-only-2026!"
    with app.state.sessions.begin() as db:
        seed_data(db, password)
    report = {
        "prompt_version": LEARNING_PROMPT_VERSION,
        "model": settings.c_llm_model or settings.llm_model,
        "backend": settings.c_llm_backend,
        "input_source": "scripted_simulated_students",
        "sessions": [],
    }

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    with TestClient(app) as client:

        def login(username):
            result = client.post(
                "/api/v1/auth/login",
                headers={"Origin": "http://testserver"},
                json={"username": username, "password": password},
            )
            result.raise_for_status()
            return {
                "Origin": "http://testserver",
                "X-CSRF-Token": result.json()["csrf_token"],
            }

        headers = login("teacher")
        course_id = client.get("/api/v1/courses").json()["items"][0]["id"]
        outline = client.get(f"/api/v1/courses/{course_id}/outline").json()
        points = {
            p["code"]: p for ch in outline["chapters"] for p in ch["knowledge_points"]
        }
        if "KP-BOUND-01" not in points:
            result = client.post(
                f"/api/v1/chapters/{outline['chapters'][0]['id']}/knowledge-points",
                headers=headers,
                json={
                    "code": "KP-BOUND-01",
                    "name": "边界值分析",
                    "definition": "选取边界及其紧邻值进行测试。",
                    "difficulty": 2,
                    "bloom_level": "apply",
                },
            )
            result.raise_for_status()
            points["KP-BOUND-01"] = result.json()
        headers = login("student01")
        for code in TEMPLATES:
            for kind in args.student_kinds:
                created = client.post(
                    "/api/v1/learning-sessions",
                    headers=headers,
                    json={
                        "course_id": course_id,
                        "knowledge_point_id": points[code]["id"],
                    },
                )
                created.raise_for_status()
                state = created.json()
                path = f"/api/v1/learning-sessions/{state['id']}"
                bad_used = False
                for _ in range(16):
                    if state["status"] == "completed":
                        break
                    stage = state["stage"]
                    answer = ANSWERS[code][
                        list(
                            ("engage", "explore", "explain", "elaborate", "evaluate")
                        ).index(stage)
                    ]
                    if not bad_used and kind == "insufficient":
                        answer = "不知道。"
                        bad_used = True
                    elif not bad_used and kind == "confused" and stage == "explore":
                        answer = CONFUSIONS[code]
                        bad_used = True
                    body = {"answer": answer}
                    if stage == "evaluate":
                        body["evaluation_choice"] = TEMPLATES[code]["quiz"]["correct"]
                    posted = client.post(path + "/turns", headers=headers, json=body)
                    if posted.status_code != 202:
                        break
                    state = client.get(path).json()
                    last = state["turns"][-1]
                    if last["status"] == "failed":
                        # Preserve and report the real failure; do not substitute a simulated success.
                        break
                record = {
                    "knowledge_point": code,
                    "student_kind": kind,
                    "session_id": state["id"],
                    "status": state["status"],
                    "stage": state["stage"],
                    "turns": state["turns"],
                }
                report["sessions"].append(record)
                with app.state.sessions() as db:
                    used_trace_ids = {
                        turn["trace_id"]
                        for item in report["sessions"]
                        for turn in item["turns"]
                    }
                    report["traces"] = [
                        {
                            "trace_id": t.trace_id,
                            "model": t.model,
                            "status": t.status,
                            "prompt_version": t.prompt_version,
                            "usage": t.usage,
                            "latency_ms": t.latency_ms,
                        }
                        for t in db.scalars(
                            select(ModelTrace).where(
                                ModelTrace.trace_id.in_(used_trace_ids)
                            )
                        )
                    ]
                save()
                print(
                    json.dumps(
                        {
                            "knowledge_point": code,
                            "student_kind": kind,
                            "status": state["status"],
                            "stage": state["stage"],
                            "turn_count": len(state["turns"]),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    report["completed"] = sum(s["status"] == "completed" for s in report["sessions"])
    report["total"] = len(report["sessions"])
    save()
    return int(report["completed"] != report["total"])


if __name__ == "__main__":
    raise SystemExit(main())
