"""Tests for knockout variants: parse_layer and build_run_config(template, cfg, mod).

Run: python3 harness/test_variants.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix  # noqa: E402
from run_matrix import build_run_config, parse_layer  # noqa: E402

SETTINGS = {"autoMemoryEnabled": True, "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "x"}]}]}}


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def _template(d, skills=True):
    d = Path(d)
    t = d / "tpl"
    t.mkdir()
    (t / "CLAUDE.md").write_text("c")
    (t / "settings.json").write_text(json.dumps(SETTINGS))
    if skills:
        src = d / "src" / "skills"
        for name in ("alpha", "quote", "zeta"):
            (src / name).mkdir(parents=True)
        os.symlink(src, t / "skills")
    return t


def test_parse_layer():
    check("plain", parse_layer("memory"), ("memory", ""))
    check("nohook", parse_layer("memory~nohook"), ("memory", "nohook"))
    check("ko", parse_layer("full~ko.quote"), ("full", "ko.quote"))


def test_nohook_strips_hooks_only():
    with tempfile.TemporaryDirectory() as d:
        t = _template(d)
        cfg = Path(d) / "cfg"
        build_run_config(t, cfg, "nohook")
        check("hooks gone, rest kept", json.loads((cfg / "settings.json").read_text()), {"autoMemoryEnabled": True})
        check("skills still the template symlink", os.readlink(cfg / "skills"), str(Path(d) / "src" / "skills"))
        check("template settings untouched", json.loads((t / "settings.json").read_text()), SETTINGS)
        build_run_config(t, cfg)
        check("no mod keeps hooks", "hooks" in json.loads((cfg / "settings.json").read_text()), True)


def test_ko_skill_dir():
    with tempfile.TemporaryDirectory() as d:
        t = _template(d)
        cfg = Path(d) / "cfg"
        build_run_config(t, cfg, "ko.quote")
        check("skills is a real dir", ((cfg / "skills").is_dir(), (cfg / "skills").is_symlink()), (True, False))
        check("knocked-out skill missing, others kept", sorted(os.listdir(cfg / "skills")), ["alpha", "zeta"])
        check("entries symlink to the snapshot", os.readlink(cfg / "skills" / "alpha"), str(Path(d) / "src" / "skills" / "alpha"))
        check("hooks untouched", "hooks" in json.loads((cfg / "settings.json").read_text()), True)
        build_run_config(t, cfg, "ko.quote")  # rebuild (retry path) is idempotent
        check("rebuild same", sorted(os.listdir(cfg / "skills")), ["alpha", "zeta"])
        build_run_config(t, cfg)
        check("no mod: plain symlink again", (cfg / "skills").is_symlink(), True)


def test_bad_mods_raise():
    with tempfile.TemporaryDirectory() as d:
        t = _template(d)
        for template, mod in ((t, "bogus"), (_template(Path(tempfile.mkdtemp(dir=d)), skills=False), "ko.quote")):
            try:
                build_run_config(template, Path(d) / "cfg", mod)
            except ValueError as e:
                print(f"  ok  {mod!r} raises: {e}")
            else:
                raise AssertionError(f"{mod!r} did not raise")


if __name__ == "__main__":
    test_parse_layer()
    test_nohook_strips_hooks_only()
    test_ko_skill_dir()
    test_bad_mods_raise()
    print("ALL PASS")
