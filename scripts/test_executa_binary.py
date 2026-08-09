#!/usr/bin/env python3
"""CI smoke test for a PyInstaller-built Executa Tool binary.

The plugins are intentionally long-running daemons (they must not exit on
stdin EOF -- Anna's Agent keeps the process alive across many invokes), so a
bare `echo ... | ./binary | assert` shell pipeline hangs forever: the binary
blocks on its second stdin.readline() waiting for input that never comes.
This script instead drives the binary as a subprocess and always terminates
it in a finally block, regardless of how much of the handshake completed.

Usage: test_executa_binary.py <binary_path> <expected_tool_name>
"""

import json
import subprocess
import sys


def send(proc: subprocess.Popen, obj: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def recv(proc: subprocess.Popen) -> dict:
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("binary exited unexpectedly (empty stdout read)")
    return json.loads(line)


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"usage: {sys.argv[0]} <binary_path> <expected_tool_name>", file=sys.stderr
        )
        return 2
    binary_path, expected_name = sys.argv[1], sys.argv[2]

    proc = subprocess.Popen(
        [binary_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stderr_text = ""
    try:
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "describe"})
        resp = recv(proc)
        assert resp["result"]["name"] == expected_name, resp
        print(f"describe: OK ({expected_name})")

        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "health"})
        resp = recv(proc)
        assert resp["result"]["status"] == "ready", resp
        print("health: OK")

        send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown"})
        resp = recv(proc)
        assert resp["result"]["ok"] is True, resp
        print("shutdown: OK")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stderr is not None:
            stderr_text = proc.stderr.read()
        if stderr_text:
            print("--- binary stderr ---", file=sys.stderr)
            print(stderr_text, file=sys.stderr)

    print("Protocol test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
