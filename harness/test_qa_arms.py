"""QA adversarial tests for item 4.1 (arms, tools: read, _model_family, wall estimate, Skill lift).

Run: python3 harness/test_qa_arms.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix as rm  # noqa: E402
import stats  # noqa: E402


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def meta_of(text):
    d = Path(tempfile.mkdtemp())
    (d / "meta.yaml").write_text(text)
    return rm.read_task_meta(d)


def test_variant_applies_adversarial():
    check("trigger set but curated none -> skipped", rm.variant_applies("skills~trigger", "none", "do it"), False)
    check("trigger set, curated 'none (why)' -> skipped", rm.variant_applies("skills~trigger", "none (proves it)", "do it"), False)
    check("trigger empty, real skill -> skipped", rm.variant_applies("skills~trigger", "humanizer", ""), False)
    check("trigger + real skill -> runs", rm.variant_applies("skills~trigger", "humanizer", "do it"), True)
    check("forced on base full, real skill -> runs", rm.variant_applies("full~forced", "humanizer", ""), True)
    check("forced, curated none -> skipped", rm.variant_applies("skills~forced", "none", ""), False)
    check("forced.<skill> on a curated-none task -> runs", rm.variant_applies("skills~forced.dev-team", "none", ""), True)
    check("ko untouched by an arm-free trigger value", rm.variant_applies("skills~ko.humanizer", "humanizer (x)", ""), True)


def test_arm_prompt_exact():
    m = {"curated_skill": "humanizer (voice)", "forced_note": "", "trigger": "T"}
    check("forced stdin starts '/<first token> '", rm.arm_prompt("BODY\n", "forced", m), ("/humanizer BODY\n", "forced", "humanizer"))
    m["forced_note"] = "NOTE"
    check("forced_note appended after a blank line", rm.arm_prompt("BODY", "forced", m)[0], "/humanizer BODY\n\nNOTE")
    check("explicit override beats curated", rm.arm_prompt("B", "forced.dev-team", m)[1:], ("forced", "dev-team"))
    check("trigger stdin = trigger + blank line + prompt", rm.arm_prompt("BODY", "trigger", m)[0], "T\n\nBODY")
    check("non-arm mods leave the prompt alone", rm.arm_prompt("BODY", "ko.x", m), ("BODY", "", ""))
    for bad in ("forced.", "forced.a b", "forced.a/../b", "forced.-x"):
        check(f"malformed {bad!r} is not an arm", rm.parse_arm(bad), ("", ""))


def test_meta_parsing_edges():
    check("unquoted value read as-is", meta_of("trigger: hello world\n")["trigger"], "hello world")
    check("trailing comment dropped", meta_of('trigger: "hi there" # note\n')["trigger"], "hi there")
    check("'#' inside the quotes kept", meta_of('trigger: "a # b" # c\n')["trigger"], "a # b")
    check("empty quoted -> empty", meta_of('trigger: ""\n')["trigger"], "")
    check("colon inside value kept", meta_of('forced_note: "n:o"\n')["forced_note"], "n:o")
    check("defaults are empty strings", (meta_of("")["trigger"], meta_of("")["forced_note"]), ("", ""))


def test_variant_error_snapshot_checks():
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d)
        (cfg / "abc" / "src" / "skills" / "real").mkdir(parents=True)
        (cfg / "abc" / "src" / "agents").mkdir(parents=True)
        (cfg / "abc" / "src" / "agents" / "agentonly.md").write_text("x")
        ok = rm.variant_error(["skills", "skills~forced.real", "skills~forced", "skills~trigger"], cfg, ["abc"])
        check("existing skill / plain arms accepted", ok, None)
        err = rm.variant_error(["skills", "skills~forced.nosuch"], cfg, ["abc"])
        check("missing skill dir rejected", bool(err) and "nosuch" in err, True)
        err = rm.variant_error(["skills", "skills~forced.agentonly"], cfg, ["abc"])
        check("skill existing only as agents/<skill>.md is rejected (skill dir required)", bool(err), True)
        check("arm on bare is rejected", bool(rm.variant_error(["bare", "bare~forced"], cfg, ["abc"])), True)
        check("arm needs its base in --layers", bool(rm.variant_error(["skills~trigger"], cfg, ["abc"])), True)


def test_tools_and_family():
    cmd = rm.build_cmd("m", ["--bare"], {"tools": "read"})
    check("exact --tools value after --bare", cmd[cmd.index("--tools") + 1], "Skill,Read,Glob,Grep")
    check("tools unset -> no --tools", "--tools" in rm.build_cmd("m", [], {}), False)
    check("tools none unchanged", rm.build_cmd("m", [], {"tools": "none"})[rm.build_cmd("m", [], {"tools": "none"}).index("--tools") + 1], "")
    for model, fam in (("opus", "opus"), ("sonnet", "sonnet"), ("claude-opus-5-5", "opus"), ("claude-sonnet-4-6", "sonnet"),
                       ("claude-haiku-4-5", "haiku"), ("claude-fable-5-1", "fable"), ("fable", "fable"), ("gpt-9", "gpt-9")):
        check(f"_model_family({model})", rm._model_family(model), fam)


def test_wall_estimate_arithmetic():
    hist = [{"task": "a", "base_model": "sonnet", "model": "sonnet:high", "wall_clock_sec": w} for w in (100, 200)]
    hist += [{"task": "m", "base_model": "sonnet", "model": "sonnet:high", "wall_clock_sec": 1000}]
    hist += [{"task": "a", "base_model": "sonnet", "model": "sonnet:high", "wall_clock_sec": 9999, "infra_error": True},
             {"task": "a", "base_model": "sonnet", "model": "sonnet:high", "wall_clock_sec": 9999, "repeat_majority": True},
             {"task": "a", "base_model": "sonnet", "model": "sonnet:high", "wall_clock_sec": 0}]
    items = [{"task": "a", "model": "sonnet", "multi_turn": False}] * 4 + [{"task": "m", "model": "sonnet", "multi_turn": True}]
    secs, lack = rm.wall_estimate(hist, items, 2, 3.0)
    check("4 one-shot x150 / 2 jobs + multi 1000, x3, none lacking", (secs, lack), ((4 * 150 / 2 + 1000) * 3, 0))
    secs, lack = rm.wall_estimate(hist, [{"task": "zzz", "model": "claude-sonnet-4-6", "multi_turn": False}], 1, 1.0)
    check("no-history cell uses family mean (100,200,1000 -> 433.33) and counts", (round(secs, 2), lack), (433.33, 1))
    secs, lack = rm.wall_estimate([], [{"task": "q", "model": "opus", "multi_turn": False}], 4)
    check("empty history -> 0s, 1 lacking", (secs, lack), (0.0, 1))
    check("wall_line format", rm.wall_line(4980, 16.0, 3), "est wall: 1h 23m (factor 16, 3 cells lack history)")
    check("stall factor constant", rm.STALL_FACTOR, 16.0)


def _lift(task, rung, passed, cost=0.1, **kw):
    r = {"task": task, "rung": rung, "passed": passed, "model": "sonnet:high", "base_model": "sonnet", "cost_usd": cost,
         "curated_skill": "humanizer", "multi_turn": False, "skill_fired": None, "infra_error": False}
    r.update(kw)
    return r


def test_skill_lift_without_base():
    lines = stats.skill_lift_section([_lift("a", "skills~forced", True)])
    text = "\n".join(lines)
    check("forced run without its skills base: header renders, no row, no crash",
          (lines[0], "humanizer" in text), ("## Skill lift", False))
    only_trig = stats.skill_lift_section([_lift("a", "skills~trigger", False, skill_fired=False),
                                          _lift("b", "skills~trigger", False, skill_fired=True),
                                          _lift("c", "skills~trigger", False, skill_fired=None)])
    check("trigger-only: routing 1/2 (None excluded), 0 pairs",
          "| humanizer | sonnet:high | 0 | n/a | n/a | n/a | 1/2 |" in "\n".join(only_trig), True)
    base_other_model = [_lift("a", "skills~forced", True), _lift("a", "skills", False, model="opus:high", base_model="opus")]
    check("base on a different model is not a pair: no row, no crash", "humanizer" in "\n".join(stats.skill_lift_section(base_other_model)), False)


if __name__ == "__main__":
    test_variant_applies_adversarial()
    test_arm_prompt_exact()
    test_meta_parsing_edges()
    test_variant_error_snapshot_checks()
    test_tools_and_family()
    test_wall_estimate_arithmetic()
    test_skill_lift_without_base()
    print("ALL PASS")
