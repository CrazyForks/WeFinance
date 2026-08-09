#!/usr/bin/env python3
"""wefinance-recommend -- Anna Executa Tool: explainable investment recommendations.

Ports the core of WeFinance's services/recommendation_service.py:
_generate_llm_recommendations() + analyze_transactions() metrics. Speaks
JSON-RPC 2.0 over stdio (Anna Executa protocol v2). Uses Anna's Sampling
capability with responseFormat=json_schema (host_capabilities: ["llm.sample"])
instead of shipping our own OpenAI key -- the strict schema replaces the
temperature=0.0 + hand-rolled JSON prompt the original service used.

See wefinance_chat.py's module docstring for the initialize()
"capabilities" vs "client_capabilities" note -- same reasoning applies here.
"""

import json
import queue
import statistics
import sys
import threading
import uuid
from collections import defaultdict

MANIFEST = {
    "name": "wefinance-recommend",
    "display_name": "WeFinance Advisor",
    "version": "0.1.0",
    "description": "Generate explainable investment recommendations grounded in the user's real spending data.",
    "author": "calderbuild",
    "host_capabilities": ["llm.sample"],
    "runtime": {"type": "uv", "min_version": "0.1.0"},
    "tools": [
        {
            "name": "generate_recommendations",
            "description": "Analyze the user's transactions and return 2-3 personalized, explainable investment recommendations.",
            "parameters": [
                {
                    "name": "transactions",
                    "type": "array",
                    "description": "List of {date: YYYY-MM-DD, amount: number, category: string} objects.",
                    "required": True,
                },
                {
                    "name": "risk_profile",
                    "type": "string",
                    "description": "One of: conservative, balanced, aggressive.",
                    "required": True,
                },
                {
                    "name": "investment_goal",
                    "type": "string",
                    "description": "Free-text investment goal, e.g. '3 年后买车首付'. Optional.",
                    "required": False,
                },
            ],
        }
    ],
}

RISK_LABELS = {
    "conservative": "保守型（不愿承受波动，追求稳健收益）",
    "balanced": "平衡型（可接受适度波动，追求收益与风险平衡）",
    "aggressive": "进取型（可承受较大波动，追求高收益）",
}

RECOMMENDATIONS_SCHEMA = {
    "name": "wefinance_recommendations",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "rationale_steps": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "risk_level": {"type": "string"},
                    },
                    "required": ["title", "summary", "rationale_steps", "risk_level"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["recommendations"],
        "additionalProperties": False,
    },
}

SAMPLING_ERROR_MESSAGES = {
    "SAMPLING_NOT_GRANTED": "You haven't enabled sampling for WeFinance Advisor yet -- turn it on in Anna Admin.",
    "SAMPLING_QUOTA_EXCEEDED": "Your account's LLM quota is used up for now.",
    "SAMPLING_PROVIDER_ERROR": "The LLM provider had an error. Try again in a moment.",
    "SAMPLING_INVALID_REQUEST": "Internal error building the request to the LLM (this is a WeFinance bug, not you).",
    "SAMPLING_TIMEOUT": "The recommendation engine took too long to respond. Try again.",
    "SAMPLING_MAX_CALLS_EXCEEDED": "This conversation turn made too many LLM calls.",
    "SAMPLING_MAX_TOKENS_EXCEEDED": "This conversation turn used up its LLM token budget.",
    "SAMPLING_NOT_NEGOTIATED": "Sampling isn't available for this session (protocol not negotiated).",
    "SAMPLING_USER_DENIED": "You declined to allow this LLM call.",
    "SAMPLING_UNSUPPORTED_RESPONSE_FORMAT": "The selected model can't produce structured output, and no fallback was configured.",
}

SAMPLING_ERROR_CODES_BY_NUMBER = {
    -32001: "SAMPLING_NOT_GRANTED",
    -32002: "SAMPLING_QUOTA_EXCEEDED",
    -32003: "SAMPLING_PROVIDER_ERROR",
    -32004: "SAMPLING_INVALID_REQUEST",
    -32005: "SAMPLING_TIMEOUT",
    -32006: "SAMPLING_MAX_CALLS_EXCEEDED",
    -32007: "SAMPLING_MAX_TOKENS_EXCEEDED",
    -32008: "SAMPLING_NOT_NEGOTIATED",
    -32009: "SAMPLING_USER_DENIED",
    -32010: "SAMPLING_UNSUPPORTED_RESPONSE_FORMAT",
}


def _friendly_sampling_error(error: dict) -> str:
    data = error.get("data") if isinstance(error, dict) else None
    code_name: str = ""
    if isinstance(data, dict) and isinstance(data.get("errorCode"), str):
        code_name = data["errorCode"]
    if not code_name:
        code_num = error.get("code") if isinstance(error, dict) else None
        code_name = (
            SAMPLING_ERROR_CODES_BY_NUMBER.get(code_num, "")
            if isinstance(code_num, int)
            else ""
        )
    return SAMPLING_ERROR_MESSAGES.get(code_name, str(error))


# --- Metrics (ported from RecommendationService.analyze_transactions,
#     re-implemented without pandas since the plugin runs as a bare subprocess)


def _monthly_average(rows: list) -> float:
    if not rows:
        return 0.0
    by_month: dict = defaultdict(float)
    for r in rows:
        month = r["date"][:7]  # YYYY-MM
        by_month[month] += r["amount"]
    return statistics.mean(by_month.values()) if by_month else 0.0


def _spending_volatility(rows: list) -> float:
    if not rows:
        return 0.0
    by_month: dict = defaultdict(float)
    for r in rows:
        by_month[r["date"][:7]] += r["amount"]
    values = list(by_month.values())
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0
    return statistics.pstdev(values) / mean


def _category_breakdown(rows: list) -> dict:
    if not rows:
        return {}
    totals: dict = defaultdict(float)
    for r in rows:
        totals[r.get("category") or "其他"] += r["amount"]
    total = sum(totals.values())
    if total == 0:
        return {}
    shares = {cat: amt / total for cat, amt in totals.items()}
    return dict(sorted(shares.items(), key=lambda item: item[1], reverse=True))


def _estimate_investable(monthly_avg: float) -> float:
    if monthly_avg <= 0:
        return 0.0
    ratio = 0.1 if monthly_avg < 3_000 else 0.2 if monthly_avg < 10_000 else 0.3
    return round(monthly_avg * ratio, 2)


def analyze_transactions(rows: list) -> dict:
    monthly_avg = _monthly_average(rows)
    return {
        "monthly_average": monthly_avg,
        "spending_volatility": _spending_volatility(rows),
        "category_breakdown": _category_breakdown(rows),
        "investable_amount": _estimate_investable(monthly_avg),
    }


# --- Reverse-RPC (Sampling) plumbing ----------------------------------------

agent_requests: queue.Queue = queue.Queue()
host_responses: dict = {}
v2_negotiated = False


def _reader() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"bad json: {exc}", file=sys.stderr)
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            )
            continue
        try:
            if not isinstance(msg, dict):
                print(f"ignoring non-object frame: {msg!r}", file=sys.stderr)
                continue
            if "method" in msg:
                agent_requests.put(msg)
            else:
                q = host_responses.pop(msg.get("id"), None)
                if q is not None:
                    q.put(msg)
        except Exception as exc:  # noqa: BLE001
            print(f"reader routing error (continuing): {exc}", file=sys.stderr)


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def sample_structured(invoke_id: str, prompt: str, *, max_tokens: int = 800) -> dict:
    if not v2_negotiated:
        raise RuntimeError(
            "Sampling unavailable: host did not negotiate protocol v2 for this session."
        )
    rid = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    host_responses[rid] = q
    _send(
        {
            "jsonrpc": "2.0",
            "id": rid,
            "method": "sampling/createMessage",
            "params": {
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": prompt}}
                ],
                "maxTokens": max_tokens,
                "temperature": 0.3,
                "includeContext": "none",
                "responseFormat": {
                    "type": "json_schema",
                    "json_schema": RECOMMENDATIONS_SCHEMA,
                },
                "onUnsupported": "json_object",
                "metadata": {"executa_invoke_id": invoke_id},
            },
        }
    )
    resp = q.get(timeout=50)
    if "error" in resp:
        raise RuntimeError(_friendly_sampling_error(resp["error"]))

    result = resp["result"]
    text = result["content"]["text"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"model did not return valid JSON: {exc}; text={text[:200]!r}"
        ) from exc

    # executa-sampling.md "Reading the result": onUnsupported="json_object"
    # asks the host to silently downgrade instead of erroring when the model
    # can't honour our strict schema. A downgraded response missing
    # "recommendations" would otherwise become success:true + empty list,
    # masking exactly the failure the schema was meant to catch.
    response_format_meta = (result.get("_meta") or {}).get("responseFormat") or {}
    if response_format_meta.get("downgraded") and "recommendations" not in data:
        raise RuntimeError(
            "Model response was downgraded from json_schema and did not contain "
            f"'recommendations': {text[:200]!r}"
        )
    return data


# --- Tool logic --------------------------------------------------------------


def build_prompt(metrics: dict, risk_profile: str, investment_goal: str) -> str:
    monthly_avg = metrics["monthly_average"]
    breakdown = metrics["category_breakdown"]
    breakdown_str = (
        "\n".join(
            f"  - {cat}: ¥{amt * monthly_avg:.2f} ({amt * 100:.1f}%)"
            for cat, amt in list(breakdown.items())[:5]
        )
        if breakdown and monthly_avg > 0
        else "  （暂无数据）"
    )
    return f"""你是一位专业的理财顾问，根据用户的真实消费数据提供个性化投资建议。

用户财务画像：
- 月均消费：¥{monthly_avg:.2f}
- 消费波动率：{metrics["spending_volatility"]:.2%}（越高说明消费越不稳定）
- 可投资金额：¥{metrics["investable_amount"]:.2f}/月
- 风险偏好：{RISK_LABELS.get(risk_profile, risk_profile)}
- 投资目标：{investment_goal or "未指定具体目标"}

消费结构（Top 5类目）：
{breakdown_str}

请基于以上数据，生成2-3条具体的理财建议。每条建议需要包含：
1. 标题（简短有力，10字以内）
2. 摘要（一句话说明这条建议的核心内容，30字左右）
3. 推理步骤（2-4步，每步解释为什么这样建议，展示可解释性）
4. 风险等级（保守型/平衡型/进取型）

要求：
- 必须基于用户的真实数据（消费金额、结构、波动率）
- 推理步骤要体现因果关系（"因为你的XX情况，所以建议YY"）
- 避免通用建议，要个性化
- 如果可投资金额很少(<500元/月)，诚实告知并给出实际可行的建议"""


def generate_recommendations(
    invoke_id: str, transactions: list, risk_profile: str, investment_goal: str
) -> list:
    metrics = analyze_transactions(transactions)
    prompt = build_prompt(metrics, risk_profile, investment_goal)
    data = sample_structured(invoke_id, prompt)
    return data.get("recommendations", [])


# --- JSON-RPC dispatch -------------------------------------------------------


def handle(req: dict) -> dict:
    global v2_negotiated
    method = req.get("method")
    req_id = req.get("id")

    if method == "describe":
        return {"jsonrpc": "2.0", "id": req_id, "result": MANIFEST}

    if method == "initialize":
        proto = (req.get("params") or {}).get("protocolVersion")
        v2_negotiated = proto == "2.0"
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2.0" if v2_negotiated else (proto or "1.1"),
                "serverInfo": {
                    "name": MANIFEST["name"],
                    "version": MANIFEST["version"],
                },
                "capabilities": {"sampling": {}} if v2_negotiated else {},
            },
        }

    if method == "health":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"status": "ready", "message": "", "details": {}},
        }

    if method == "shutdown":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"ok": True}}

    if method == "invoke":
        params = req.get("params") or {}
        tool = params.get("tool")
        args = params.get("arguments") or {}
        ctx = params.get("context") or {}
        invoke_id = str(ctx.get("invoke_id") or req_id)

        if tool != "generate_recommendations":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"unknown tool: {tool}"},
            }

        transactions = args.get("transactions") or []
        risk_profile = args.get("risk_profile", "balanced")
        investment_goal = args.get("investment_goal", "")

        if not transactions:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "success": False,
                    "error": "transactions is required and must be non-empty",
                },
            }

        try:
            recs = generate_recommendations(
                invoke_id, transactions, risk_profile, investment_goal
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"success": True, "data": {"recommendations": recs}},
            }
        except Exception as exc:  # noqa: BLE001
            print(f"generate_recommendations failed: {exc}", file=sys.stderr)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"success": False, "error": str(exc)},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"unknown method: {method}"},
    }


def main() -> None:
    threading.Thread(target=_reader, daemon=True).start()
    while True:
        req = agent_requests.get()
        _send(handle(req))


if __name__ == "__main__":
    main()
