"""CLAUDE_CODE_MAX_OUTPUT_TOKENS must survive the credential scrub (its name contains TOKEN)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from contamination import scrub_env  # noqa: E402
from run_matrix import ENV_KEEP  # noqa: E402


def test_cap_kept_credentials_dropped():
    env = {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32000", "CLAUDE_CODE_OAUTH_TOKEN": "x", "GH_TOKEN": "y", "PATH": "p"}
    out = scrub_env(env, set() | ENV_KEEP)
    assert out == {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32000", "PATH": "p"}, out


def test_without_keep_it_is_dropped():
    assert "CLAUDE_CODE_MAX_OUTPUT_TOKENS" not in scrub_env({"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "1"}, set())


if __name__ == "__main__":
    test_cap_kept_credentials_dropped()
    test_without_keep_it_is_dropped()
    print("ok")
