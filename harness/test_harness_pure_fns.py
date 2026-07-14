"""Tests for three pure functions in run_matrix: detect_skill_fired, _parse_stream,
looks_like_auth_error.

Run: python3 harness/test_harness_pure_fns.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_matrix import detect_skill_fired, _parse_stream, looks_like_auth_error  # noqa: E402


def check(label, got, want):
    assert got == want, f"{label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


# ---------------------------------------------------------------------------
# detect_skill_fired
# ---------------------------------------------------------------------------

def _make_skill_event(skill_name: str) -> dict:
    """Craft an assistant event with a Skill tool_use block."""
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Skill",
                    "input": {"skill": skill_name},
                }
            ]
        },
    }


def test_detect_skill_fired_match():
    events = [_make_skill_event("dev-team-auto")]
    result = detect_skill_fired(events, "dev-team-auto")
    check("detect_skill_fired: matching curated skill → True", result, True)


def test_detect_skill_fired_no_match():
    events = [_make_skill_event("some-other-skill")]
    result = detect_skill_fired(events, "dev-team-auto")
    check("detect_skill_fired: non-matching skill → False", result, False)


def test_detect_skill_fired_empty_trace():
    result = detect_skill_fired([], "dev-team-auto")
    check("detect_skill_fired: empty trace → False (no events, skill present)", result, False)


def test_detect_skill_fired_no_intended_skill():
    # When intended_skill is empty string, should return None
    result = detect_skill_fired([_make_skill_event("dev-team")], "")
    check("detect_skill_fired: empty intended_skill → None", result, None)


# ---------------------------------------------------------------------------
# _parse_stream
# ---------------------------------------------------------------------------

def test_parse_stream_valid_with_result():
    usage = {"input_tokens": 100, "output_tokens": 50}
    result_event = {
        "type": "result",
        "result": "Task complete",
        "is_error": False,
        "num_turns": 3,
        "total_cost_usd": 0.002,
        "usage": usage,
    }
    stream = json.dumps(result_event) + "\n"
    transcript, events = _parse_stream(stream, "")
    check("_parse_stream: result text", transcript["result"], "Task complete")
    check("_parse_stream: usage dict", transcript["usage"], usage)
    check("_parse_stream: is_error", transcript["is_error"], False)
    check("_parse_stream: events list length", len(events), 1)


def test_parse_stream_truncated():
    # Truncated JSON: final closing brace cut off — should not crash.
    truncated = '{"type":"result","result":"done","is_error":false'
    try:
        transcript, events = _parse_stream(truncated, "something went wrong")
        # If it returns rather than raises, it should be a synthesized error transcript.
        check("_parse_stream: truncated returns is_error=True", transcript["is_error"], True)
        check("_parse_stream: truncated events list", events, [])
    except Exception as exc:  # pragma: no cover
        assert False, f"_parse_stream raised unexpectedly on truncated input: {exc}"


def test_parse_stream_no_result_event():
    # Stream has assistant events but no terminal result event — should synthesize one.
    assistant_event = {
        "type": "assistant",
        "message": {
            "usage": {"input_tokens": 42, "output_tokens": 7},
            "content": [],
        },
    }
    stream = json.dumps(assistant_event) + "\n"
    transcript, events = _parse_stream(stream, "timeout reached")
    check("_parse_stream: no result → is_error synthesized", transcript["is_error"], True)
    check("_parse_stream: no result → salvaged usage", transcript["usage"],
          {"input_tokens": 42, "output_tokens": 7})


# ---------------------------------------------------------------------------
# looks_like_auth_error
# ---------------------------------------------------------------------------

def test_looks_like_auth_error_authentication_keyword():
    # _AUTH_ERR_PATTERNS contains "authentication_error" (lowercase, underscore)
    result = looks_like_auth_error(
        "", "", {"result": "authentication_error: token rejected"}
    )
    check("looks_like_auth_error: 'authentication_error' pattern → True", result, True)


def test_looks_like_auth_error_401():
    # hay is built from stderr + transcript result; stdout is not checked
    result = looks_like_auth_error(
        "", "HTTP 401 Unauthorized", {"result": ""}
    )
    check("looks_like_auth_error: '401' in stderr → True", result, True)


def test_looks_like_auth_error_unauthorized():
    # "unauthorized" is in _AUTH_ERR_PATTERNS; "403" is not
    result = looks_like_auth_error(
        "", "", {"result": "unauthorized: token has expired"}
    )
    check("looks_like_auth_error: 'unauthorized' in transcript → True", result, True)


def test_looks_like_auth_error_unrelated_error():
    result = looks_like_auth_error(
        "", "", {"result": "KeyError: 'missing_key'"}
    )
    check("looks_like_auth_error: KeyError → False", result, False)


def test_looks_like_auth_error_file_not_found():
    result = looks_like_auth_error(
        "", "", {"result": "FileNotFoundError: /tmp/missing.txt"}
    )
    check("looks_like_auth_error: FileNotFoundError → False", result, False)


if __name__ == "__main__":
    test_detect_skill_fired_match()
    test_detect_skill_fired_no_match()
    test_detect_skill_fired_empty_trace()
    test_detect_skill_fired_no_intended_skill()

    test_parse_stream_valid_with_result()
    test_parse_stream_truncated()
    test_parse_stream_no_result_event()

    test_looks_like_auth_error_authentication_keyword()
    test_looks_like_auth_error_401()
    test_looks_like_auth_error_unauthorized()
    test_looks_like_auth_error_unrelated_error()
    test_looks_like_auth_error_file_not_found()

    print("ALL PASS")
