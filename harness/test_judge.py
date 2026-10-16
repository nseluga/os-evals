"""Tests for harness/judge.py (no model calls).

Covers: prompt carries no run identity, parse_judge_output paths, skip rules, leak_terms,
artifact cap/truncation + diff vs seed, Agent == Task in the digest, judge_cmd flags.

Run: python3 harness/test_judge.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge  # noqa: E402


def check(label, got, want):
    assert got == want, f"FAIL {label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def raises(label, fn):
    try:
        fn()
    except judge.JudgeError:
        print(f"  ok  {label}: JudgeError")
        return
    raise AssertionError(f"FAIL {label}: expected JudgeError")


def _task(tmp, rubric="# R\n5: great\n", meta="category: writing\n"):
    d = Path(tmp) / "tasks" / "writing" / "demo"
    (d).mkdir(parents=True)
    if rubric is not None:
        (d / "rubric.md").write_text(rubric)
    (d / "meta.yaml").write_text(meta)
    return d


def test_prompt_has_no_run_identity():
    with tempfile.TemporaryDirectory() as tmp:
        d = _task(tmp)
        run = Path(tmp) / "runs" / "20261002T112834Z_writing-demo_bare_sonnet_r1.json"
        run.parent.mkdir()
        ws = Path(tmp) / "ws" / "w-abc1234567" / "w"
        ws.mkdir(parents=True)
        run.write_text(json.dumps({"result": "the answer", "_meta": {
            "task": "writing/demo", "rung": "memory~nohook", "layer": "memory", "model": "sonnet",
            "workspace_dir": str(ws), "os_sha": "34b1958"}}))
        art, trunc = judge.artifact_text(run, Path(tmp) / "tasks")
        prompt = judge.build_judge_prompt((d / "rubric.md").read_text(), art)
        for leak in ("memory~nohook", "sonnet", "34b1958", str(ws), "w-abc1234567", run.stem, "r1.json",
                     "writing-demo"):
            check(f"prompt lacks {leak!r}", leak in prompt, False)
        check("prompt has rubric", "<rubric>" in prompt and "5: great" in prompt, True)
        check("prompt has artifact", "the answer" in prompt, True)
        check("cmd carries no run identity", any("sonnet" in a for a in judge.judge_cmd()), False)


def test_judge_cmd_flags():
    c = judge.judge_cmd("SYS")
    for flag in ("--bare", "--no-session-persistence", "--json-schema"):
        check(f"flag {flag}", flag in c, True)
    check("model", c[c.index("--model") + 1], "opus")
    check("effort", c[c.index("--effort") + 1], "medium")
    check("tools empty", c[c.index("--tools") + 1], "")
    check("budget", c[c.index("--max-budget-usd") + 1], "0.5")
    check("system prompt", c[c.index("--system-prompt") + 1], "SYS")
    check("json out", c[c.index("--output-format") + 1], "json")


def test_parse_paths():
    good = {"score": 4, "rationale": "solid"}
    out = judge.parse_judge_output(json.dumps({"structured_output": good, "result": "{\"score\": 1}",
                                               "total_cost_usd": 0.07}))
    check("structured_output wins", (out["score"], out["cost_usd"]), (4, 0.07))
    out = judge.parse_judge_output(json.dumps(
        {"result": 'Here: {"score": 2, "rationale": "a"} then {"score": 3, "rationale": "b {x}"}'}))
    check("last JSON object in result", (out["score"], out["rationale"]), (3, "b {x}"))
    out = judge.parse_judge_output(json.dumps({"structured_output": {"rationale": "no score"},
                                               "result": '{"score": 5, "rationale": "r"}'}))
    check("falls back when structured lacks score", out["score"], 5)
    raises("no score anywhere", lambda: judge.parse_judge_output(json.dumps({"result": "hello"})))
    raises("not json", lambda: judge.parse_judge_output("oops"))
    raises("is_error", lambda: judge.parse_judge_output(json.dumps({"is_error": True, "result": "boom"})))
    raises("score above 5", lambda: judge.parse_judge_output(json.dumps({"structured_output": {"score": 9, "rationale": ""}})))
    raises("score non-integer", lambda: judge.parse_judge_output(json.dumps({"structured_output": {"score": 3.5, "rationale": ""}})))


def test_skip_rules():
    with tempfile.TemporaryDirectory() as tmp:
        d = _task(tmp)
        ok = {"result": "text", "_meta": {}}
        check("judge it", judge.skip_reason(ok, d, []), None)
        check("empty result", judge.skip_reason({"result": "  ", "_meta": {}}, d, []), "no result")
        check("is_error", judge.skip_reason({"result": "x", "is_error": True, "_meta": {}}, d, []), "no result")
        check("contaminated", judge.skip_reason({"result": "x", "_meta": {"contaminated": True}}, d, []), "contaminated")
        nod = _task(Path(tmp) / "other", rubric=None)
        check("no rubric", judge.skip_reason(ok, nod, []), "no rubric")
        sha = judge.rubric_sha(d)
        hit = {"rubric_sha": sha, "model": "opus", "effort": "medium"}
        check("sidecar hit", judge.skip_reason(ok, d, [hit]), "already judged")
        for k, v in (("rubric_sha", "zzz"), ("model", "sonnet"), ("effort", "high")):
            check(f"sidecar differs in {k} -> rejudge", judge.skip_reason(ok, d, [{**hit, k: v}]), None)
        (d / "rubric.md").write_text("# R changed\n")
        check("rubric edit changes sha", judge.rubric_sha(d) != sha, True)
        check("edited rubric -> rejudge", judge.skip_reason(ok, d, [hit]), None)
        (d / "meta.yaml").write_text("category: coding\njudge_files: a.py\n")
        check("judged files with workspace gone", judge.skip_reason(
            {"result": "x", "_meta": {"workspace_dir": "/nonexistent/w"}}, d, []), "workspace gone")


def test_leak_terms():
    skills = ["dev-team", "quote", "map", "dt-qa"]
    check("hyphenated skill name", judge.leak_terms("Used the dev-team skill well", skills), ["dev-team"])
    check("hyphen name not inside another word", judge.leak_terms("dev-teams are fine; xdt-qa", skills), [])
    check("plain word is not a leak", judge.leak_terms("A good quote and a map of the module", skills), [])
    check("slash form is a leak", judge.leak_terms("it followed /quote", skills), ["quote"])
    check("'quote skill' is a leak", judge.leak_terms("the Quote skill was applied", skills), ["quote"])
    check("CLAUDE.md and my memory", judge.leak_terms("per CLAUDE.md and my memory", skills), ["claude.md", "my memory"])
    check("clean rationale", judge.leak_terms("Names all three flaws.", skills), [])


def test_artifact_cap_and_diff():
    with tempfile.TemporaryDirectory() as tmp:
        ws, seed = Path(tmp) / "w", Path(tmp) / "seed"
        ws.mkdir()
        seed.mkdir()
        (seed / "h.py").write_text("a = 1\nb = 2\n")
        (ws / "h.py").write_text("a = 1\nb = 3\n")
        art, trunc = judge.build_artifact("done", ["h.py"], ws, seed)
        check("short not truncated", trunc, False)
        check("diff markers", "-b = 2" in art and "+b = 3" in art, True)
        check("diff labels carry no abs path", str(ws) in art, False)
        check("final response included", "## Final response\ndone" in art, True)
        (ws / "new.txt").write_text("fresh")
        art, _ = judge.build_artifact("", ["new.txt", "missing.txt"], ws, seed)
        check("new file shown whole", "fresh" in art, True)
        check("missing file named", "(not present)" in art, True)
        big = "x" * (judge.ARTIFACT_CAP + 500)
        art, trunc = judge.build_artifact(big, [], None, seed)
        check("long result truncated", trunc, True)
        check("capped near 8 KB", len(art) <= judge.ARTIFACT_CAP + 40, True)
        check("truncation marked", art.endswith("[... truncated]"), True)
        art, trunc = judge.build_artifact("x" * (judge.ARTIFACT_CAP - len("## Final response\n")), [], None, seed)
        check("exactly at cap not truncated", trunc, False)


def _ev(*uses):
    return [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": n, "input": i} for n, i in uses]}}]


def test_agent_equals_task_digest():
    spawn = {"subagent_type": "dt-engineer", "model": "sonnet", "description": "build it", "prompt": "SECRET PROMPT"}
    a = judge.trace_digest(_ev(("Agent", spawn), ("Bash", {"command": "ls"})))
    t = judge.trace_digest(_ev(("Task", spawn), ("Bash", {"command": "ls"})))
    check("Agent and Task digest identical", a, t)
    check("digest line", a.splitlines()[0], "- Agent subagent_type=dt-engineer model=sonnet build it")
    check("prompt body not in digest", "SECRET" in a, False)
    long = judge.trace_digest(_ev(*[("Bash", {"command": "x" * 100})] * 100))
    check("digest capped", len(long) <= judge.DIGEST_CAP + 30, True)


def test_process_digest_only_for_process_tasks():
    with tempfile.TemporaryDirectory() as tmp:
        for cat, want in (("process", True), ("writing", False)):
            d = Path(tmp) / cat / "tasks" / "p" / "t"
            d.mkdir(parents=True)
            (d / "meta.yaml").write_text(f"category: {cat}\n")
            run = Path(tmp) / cat / "run.json"
            run.write_text(json.dumps({"result": "r", "_meta": {"task": "p/t"}}))
            run.with_name("run.trace.jsonl").write_text(
                "\n".join(json.dumps(e) for e in _ev(("Task", {"subagent_type": "dt-qa", "description": "d"}))))
            art, _ = judge.artifact_text(run, Path(tmp) / cat / "tasks")
            check(f"{cat}: digest present", "## Tool-use digest" in art and "- Agent subagent_type=dt-qa" in art, want)


def test_meta_column0_guard():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "meta.yaml").write_text("category: coding\njudge_files: a.py, b.html\ndescription: |\n  judge_files: evil.py\n  category: process\n")
        m = judge.read_judge_meta(d)
        check("judge_files column-0 only", m["judge_files"], ["a.py", "b.html"])
        check("category column-0 only", m["category"], "coding")


def test_sidecar_roundtrip_and_validate_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "20261002T000000Z_t_bare_sonnet.json"
        check("sidecar name", judge.sidecar_path(p).name, "20261002T000000Z_t_bare_sonnet.judge.jsonl")
        side = judge.sidecar_path(p)
        side.write_text('{"score": 3}\nnot json\n{"score": 4}\n')
        check("tolerant reader", [e["score"] for e in judge.read_sidecar(side)], [3, 4])
        # --validate must not write sidecars into tasks/
        d = _task(tmp)
        (d / "tests" / "good").mkdir(parents=True)
        (d / "tests" / "bad").mkdir(parents=True)
        (d / "tests" / "good" / "transcript.json").write_text('{"result": "great"}')
        (d / "tests" / "bad" / "transcript.json").write_text('{"result": "bad"}')
        scores = iter([5, 1])
        orig = judge.call_judge
        judge.call_judge = lambda prompt, c, s, timeout=300: {"score": next(scores), "rationale": "r", "cost_usd": 0.01}
        orig_sha = judge.latest_sha
        judge.latest_sha = lambda c, s="": "x"
        try:
            before = sorted(str(x) for x in Path(tmp).rglob("*"))
            check("validate OK on 5/1", judge.validate_task("writing/demo", Path(tmp) / "tasks", Path(tmp)), 0)
            check("validate wrote no files", sorted(str(x) for x in Path(tmp).rglob("*")), before)
            scores = iter([3, 1])
            check("validate MISMATCH on 3/1", judge.validate_task("writing/demo", Path(tmp) / "tasks", Path(tmp)), 1)
        finally:
            judge.call_judge, judge.latest_sha = orig, orig_sha


if __name__ == "__main__":
    test_prompt_has_no_run_identity()
    test_judge_cmd_flags()
    test_parse_paths()
    test_skip_rules()
    test_leak_terms()
    test_artifact_cap_and_diff()
    test_agent_equals_task_digest()
    test_process_digest_only_for_process_tasks()
    test_meta_column0_guard()
    test_sidecar_roundtrip_and_validate_writes_nothing()
    print("ALL PASS")
