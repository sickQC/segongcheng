"""Exercise the actual JSON stream protocol with a local, non-network child."""

import json
import os
import subprocess
import sys
import time

import pytest

from app.services.c_model_gateway import ModelCallError, read_codex_reply


def child(events, *, hang=False, stderr=""):
    script = (
        "import sys,json,time\nsys.stdin.read()\n"
        f"print({stderr!r},file=sys.stderr,flush=True)\n"
        f"events=json.loads({json.dumps(json.dumps(events))})\n"
        "for event in events: print(json.dumps(event),flush=True)\n" + ("time.sleep(30)\n" if hang else "")
    )
    return subprocess.Popen(
        [sys.executable, "-u", "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )


MESSAGE = {"type": "item.completed", "item": {"type": "agent_message", "text": '{"ok":true}'}}
DONE = {"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 4}}


def test_reconnect_then_success_does_not_wait_for_cli_shutdown():
    process = child(
        [{"type": "error", "message": "Reconnecting... stream disconnected"}, MESSAGE, DONE], hang=True
    )
    started = time.monotonic()
    reply = read_codex_reply(process, "synthetic prompt", 3, "configured-model")
    assert json.loads(reply.text) == {"ok": True}
    assert reply.usage["total_tokens"] == 16
    assert reply.details["reconnect_count"] == 1
    assert process.poll() is not None
    assert time.monotonic() - started < 6


@pytest.mark.parametrize(
    "events, expected",
    [
        ([MESSAGE], "INCOMPLETE_MODEL_RESPONSE"),
        (
            [MESSAGE, {"type": "turn.failed", "error": {"message": "model is not supported"}}],
            "MODEL_NOT_AVAILABLE",
        ),
        ([{"type": "item.started", "item": {"type": "command_execution"}}, DONE], "UNEXPECTED_TOOL_USE"),
        ([DONE], "EMPTY_MODEL_RESPONSE"),
    ],
)
def test_partial_failed_and_tool_responses_are_rejected(events, expected):
    process = child(events)
    with pytest.raises(ModelCallError) as error:
        read_codex_reply(process, "synthetic prompt", 3, "configured-model")
    assert error.value.code == expected
    assert process.poll() is not None


def test_timeout_retains_only_safe_network_signals():
    process = child(
        [],
        hang=True,
        stderr="failed to connect to websocket: tls handshake eof https://private.example/secret",
    )
    with pytest.raises(ModelCallError) as error:
        read_codex_reply(process, "private prompt", 1, "configured-model")
    assert error.value.code == "MODEL_TIMEOUT"
    assert "tls_handshake_eof" in error.value.details["transport_signals"]
    assert "private" not in json.dumps(error.value.details)
    assert "secret" not in json.dumps(error.value.details)
    assert process.poll() is not None
