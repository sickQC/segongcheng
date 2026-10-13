"""大模型客户端（OpenAI 兼容 + 离线兜底）与成本核算。

课程验收把"智能功能必须真实调用大模型"列为否决项 X1，因此：
  - provider="openai" 是**唯一**可用于验收的路径；
  - provider="offline" 的抽取式回答仅用于本地开发、单元测试与无网演示，
    并且在每一条输出上都显式标注"离线抽取式（未调用大模型）"，不会被误当成智能体。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Iterator

import httpx

from .config import LLMConfig
from .textutil import split_sentences, strip_markdown, tokenize, truncate

# 每 100 万 token 的价格（美元），仅用于**估算**成本；以官方价目为准。
PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "deepseek-chat": (0.27, 1.10),
    "qwen-plus": (0.40, 1.20),
    "qwen-turbo": (0.05, 0.20),
}


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    degraded: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_ms": round(self.latency_ms, 1),
            "cost_usd": round(self.cost_usd, 6),
            "degraded": self.degraded,
            "error": self.error,
        }


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：中文约 1 字 ≈ 0.75 token，英文按空白词计。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    other = len(re.findall(r"[A-Za-z0-9]+", text or ""))
    return int(cjk * 0.75 + other * 1.3) + 4


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICE_PER_MTOK.get(model.lower())
    if not price:
        return 0.0
    pin, pout = price
    return prompt_tokens / 1e6 * pin + completion_tokens / 1e6 * pout


class BaseLLM:
    provider = "base"

    def __init__(self, cfg: LLMConfig) -> None:
        self.cfg = cfg

    def complete(self, system: str, user: str) -> LLMResult:
        raise NotImplementedError

    def stream(self, system: str, user: str) -> Iterator[str]:
        yield self.complete(system, user).text


class OpenAICompatLLM(BaseLLM):
    provider = "openai"

    def __init__(self, cfg: LLMConfig) -> None:
        super().__init__(cfg)
        self._client = httpx.Client(timeout=cfg.timeout_s)
        self.last_usage: dict = {}

    def _payload(self, system: str, user: str, *, stream: bool) -> dict:
        return {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
            "stream": stream,
        }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }

    def complete(self, system: str, user: str) -> LLMResult:
        url = f"{self.cfg.base_url.rstrip('/')}/chat/completions"
        last_err = ""
        for attempt in range(self.cfg.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self._client.post(
                    url, headers=self._headers(), json=self._payload(system, user, stream=False)
                )
                if resp.status_code >= 500 or resp.status_code == 429:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                data = resp.json()
                text = (data["choices"][0]["message"].get("content") or "").strip()
                usage = data.get("usage") or {}
                pt = int(usage.get("prompt_tokens") or estimate_tokens(system + user))
                ct = int(usage.get("completion_tokens") or estimate_tokens(text))
                model = data.get("model") or self.cfg.model
                return LLMResult(
                    text=text,
                    model=model,
                    provider=self.provider,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    cost_usd=estimate_cost(self.cfg.model, pt, ct),
                )
            except Exception as exc:  # noqa: BLE001 —— 记录后按策略降级（NF-5）
                last_err = f"{type(exc).__name__}: {exc}"
                if attempt < self.cfg.max_retries:
                    time.sleep(0.6 * (attempt + 1))
        return LLMResult(
            text="",
            model=self.cfg.model,
            provider=self.provider,
            latency_ms=0.0,
            degraded=True,
            error=last_err,
        )

    def stream(self, system: str, user: str) -> Iterator[str]:
        url = f"{self.cfg.base_url.rstrip('/')}/chat/completions"
        try:
            with self._client.stream(
                "POST", url, headers=self._headers(), json=self._payload(system, user, stream=True)
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        delta = json.loads(chunk)["choices"][0].get("delta", {})
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    piece = delta.get("content")
                    if piece:
                        yield piece
        except Exception as exc:  # noqa: BLE001
            yield f"\n\n[流式输出中断：{type(exc).__name__}]"


OFFLINE_BANNER = (
    "> ⚠️ **检索演示回答（未调用大模型）**\n"
    "> 本段由检索到的证据直接抽取拼接而成，用于本地演示与自动化测试；"
    "在 `.env` 中配置 `LLM_API_KEY` 与 `LLM_MODEL` 后，`mode=live` 会走真实模型调用。\n\n"
)

def _clean_sentence(sentence: str) -> str:
    """去掉抽取句子里残留的 Markdown 标记与列表符号，让离线答案可读。"""
    return strip_markdown(sentence)


def _pick_sentences(
    scored: list[tuple[float, int, str]], *, limit: int = 6
) -> list[tuple[float, int, str]]:
    """从打分后的句子中挑出不重复、且尽量覆盖多个证据片段的句子。"""
    picked: list[tuple[float, int, str]] = []
    seen: set[str] = set()
    per_evidence: dict[int, int] = {}
    for overlap, idx, sent in scored:
        clean = _clean_sentence(sent)
        if len(clean) < 8 or clean in seen:
            continue
        if per_evidence.get(idx, 0) >= 2:  # 单个片段最多贡献 2 句，避免上下文被一节占满
            continue
        if overlap <= 0 and picked:  # 已有正相关句子时，不再凑无关句
            continue
        seen.add(clean)
        per_evidence[idx] = per_evidence.get(idx, 0) + 1
        picked.append((overlap, idx, clean))
        if len(picked) >= limit:
            break
    return picked


class OfflineExtractiveLLM(BaseLLM):
    """无网兜底：从检索到的证据里抽最相关的句子拼成答案，并带上引用编号。

    它**不是**智能体，只是保证系统在无 API Key 时也能端到端跑通、被测试与被评测。
    """

    provider = "offline"

    def complete(self, system: str, user: str) -> LLMResult:
        t0 = time.perf_counter()
        question = ""
        evidence: list[tuple[int, str]] = []
        for block in re.finditer(r"\[(\d+)\] 来源：.*?\n<<<EVIDENCE\n(.*?)\nEVIDENCE>>>", user, re.DOTALL):
            evidence.append((int(block.group(1)), block.group(2)))
        m = re.search(r"【学生问题】\s*(.+)", user)
        if m:
            question = m.group(1).strip()
        if not question:
            question = user.strip().splitlines()[-1] if user.strip() else ""

        q_tokens = set(tokenize(question))
        scored: list[tuple[float, int, str]] = []
        for idx, text in evidence:
            for sent in split_sentences(text):
                s = sent.strip()
                if len(s) < 10:
                    continue
                st = set(tokenize(s))
                if not st:
                    continue
                overlap = len(q_tokens & st) / max(1, len(q_tokens))
                scored.append((overlap, idx, s))
        scored.sort(key=lambda x: -x[0])
        picked = _pick_sentences(scored, limit=6)

        if not evidence:
            body = "资料中没有找到与该问题相关的内容，我不做推测。建议换一个课程内的知识点提问。"
        elif not picked:
            body = "资料中提到过相关主题，但没有直接回答该问题的句子。以下是资料原文，供你自行核对。"
        else:
            body = "根据检索到的课程资料：\n\n" + "\n".join(
                f"- {truncate(s, 180)} [{idx}]" for _, idx, s in picked
            )

        text = OFFLINE_BANNER + body
        return LLMResult(
            text=text,
            model="offline-extractive",
            provider=self.provider,
            prompt_tokens=estimate_tokens(system + user),
            completion_tokens=estimate_tokens(text),
            latency_ms=(time.perf_counter() - t0) * 1000,
            cost_usd=0.0,
            degraded=True,
        )

    def stream(self, system: str, user: str) -> Iterator[str]:
        text = self.complete(system, user).text
        step = 12
        for i in range(0, len(text), step):
            yield text[i : i + step]


def get_llm(cfg: LLMConfig) -> BaseLLM:
    if cfg.provider == "openai" and cfg.api_key:
        return OpenAICompatLLM(cfg)
    return OfflineExtractiveLLM(cfg)
