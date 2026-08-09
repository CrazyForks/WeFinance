#!/usr/bin/env python3
"""Local smoke test for wefinance-recommend's plugin.py.

Same approach as wefinance-chat/test_local.py: spawn the plugin as a real
subprocess and play the "host" role ourselves, answering the plugin's
sampling/createMessage reverse RPC with a fake structured completion so the
full describe -> initialize -> invoke -> sampling(json_schema) -> return
round trip is exercised against the real wire protocol.
"""

import json
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).parent / "wefinance_recommend.py"

FAKE_RECS = {
    "recommendations": [
        {
            "title": "建立应急储备金",
            "summary": "先攒3-6个月生活费再谈投资",
            "rationale_steps": ["你的月消费波动率较高", "先有缓冲垫再投资更稳妥"],
            "risk_level": "保守型",
        }
    ]
}

SAMPLE_TRANSACTIONS = [
    {"date": "2026-06-05", "amount": 240.0, "category": "餐饮"},
    {"date": "2026-06-15", "amount": 30.0, "category": "交通"},
    {"date": "2026-07-05", "amount": 300.0, "category": "餐饮"},
    {"date": "2026-07-20", "amount": 50.0, "category": "交通"},
]


def send(proc: subprocess.Popen, obj: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def recv(proc: subprocess.Popen) -> dict:
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("plugin exited unexpectedly (empty stdout read)")
    return json.loads(line)


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, str(PLUGIN)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert (
        proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    )

    try:
        # 1. describe
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "describe"})
        resp = recv(proc)
        assert resp["result"]["name"] == "wefinance-recommend", resp
        assert resp["result"]["tools"][0]["name"] == "generate_recommendations", resp
        print("describe: OK")

        # 2. initialize
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {"protocolVersion": "2.0"},
            },
        )
        resp = recv(proc)
        assert resp["result"]["protocolVersion"] == "2.0", resp
        print("initialize: OK")

        # 3. invoke with no transactions -> should fail gracefully, not crash
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "invoke",
                "params": {
                    "tool": "generate_recommendations",
                    "arguments": {"transactions": [], "risk_profile": "balanced"},
                },
            },
        )
        resp = recv(proc)
        assert resp["result"]["success"] is False, resp
        print("empty-transactions guard: OK")

        # 4. real invoke -> plugin computes metrics itself, then emits a
        #    reverse RPC asking for a json_schema-constrained completion
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "invoke",
                "params": {
                    "tool": "generate_recommendations",
                    "arguments": {
                        "transactions": SAMPLE_TRANSACTIONS,
                        "risk_profile": "conservative",
                        "investment_goal": "3年后买车首付",
                    },
                    "context": {"invoke_id": "test-invoke-2"},
                },
            },
        )

        reverse_rpc = recv(proc)
        assert reverse_rpc["method"] == "sampling/createMessage", reverse_rpc
        rf = reverse_rpc["params"]["responseFormat"]
        assert rf["type"] == "json_schema", rf
        assert rf["json_schema"]["name"] == "wefinance_recommendations", rf
        # sanity: the prompt should reference the real computed monthly average
        # (540/2 months = 270 dining + 40 transit -> monthly_average ~= 310)
        prompt_text = reverse_rpc["params"]["messages"][0]["content"]["text"]
        assert "月均消费" in prompt_text, prompt_text
        assert "3年后买车首付" in prompt_text, prompt_text
        print(
            "sampling/createMessage request (json_schema): OK (well-formed, metrics embedded)"
        )

        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": reverse_rpc["id"],
                "result": {
                    "role": "assistant",
                    "content": {"type": "text", "text": json.dumps(FAKE_RECS)},
                },
            },
        )

        final = recv(proc)
        assert final["id"] == 4, final
        assert final["result"]["success"] is True, final
        assert (
            final["result"]["data"]["recommendations"] == FAKE_RECS["recommendations"]
        ), final
        print(
            "invoke generate_recommendations: OK (round trip returned fake recs unchanged)"
        )

        # 5. a *downgraded* sampling response missing "recommendations" must
        #    surface as a clean failure, not a silent success with an empty list
        #    (executa-sampling.md _meta.responseFormat.downgraded).
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "invoke",
                "params": {
                    "tool": "generate_recommendations",
                    "arguments": {
                        "transactions": SAMPLE_TRANSACTIONS,
                        "risk_profile": "balanced",
                    },
                    "context": {"invoke_id": "test-invoke-downgrade"},
                },
            },
        )
        reverse_rpc = recv(proc)
        assert reverse_rpc["method"] == "sampling/createMessage", reverse_rpc
        send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": reverse_rpc["id"],
                "result": {
                    "role": "assistant",
                    "content": {"type": "text", "text": "{}"},
                    "_meta": {
                        "responseFormat": {
                            "requested": "json_schema",
                            "applied": "json_object",
                            "structuredValid": True,
                            "downgraded": True,
                        }
                    },
                },
            },
        )
        final = recv(proc)
        assert final["id"] == 5, final
        assert final["result"]["success"] is False, final
        assert "downgraded" in final["result"]["error"].lower(), final
        print("downgraded-response guard: OK (surfaced as failure, not empty success)")

        # 6. health -- executa-lifecycle.md's documented shape
        send(proc, {"jsonrpc": "2.0", "id": 6, "method": "health"})
        resp = recv(proc)
        assert resp["result"]["status"] == "ready", resp
        print("health: OK")

        # 7. malformed JSON on stdin -> documented -32700 parse error, and
        #    the reader thread must survive it (not silently die).
        assert proc.stdin is not None
        proc.stdin.write("not valid json\n")
        proc.stdin.flush()
        resp = recv(proc)
        assert resp["error"]["code"] == -32700, resp
        print("malformed JSON: OK (-32700, reader thread survived)")

        # 8. shutdown handler
        send(proc, {"jsonrpc": "2.0", "id": 8, "method": "shutdown"})
        resp = recv(proc)
        assert resp["result"]["ok"] is True, resp
        print("shutdown: OK")

        assert proc.poll() is None, "plugin exited after handling requests (pitfall #1)"
        print("long-running check: OK (process still alive)")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr = proc.stderr.read()
        if stderr:
            print("--- plugin stderr ---", file=sys.stderr)
            print(stderr, file=sys.stderr)

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
