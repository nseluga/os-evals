"""Tests: parser robustness, no_result meta, trace without _meta, layer/draft guards, load_rung.

Run: python3 harness/test_run_guards.py
"""
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_matrix  # noqa: E402
from run_matrix import _iter_tool_uses, _parse_stream, load_rung  # noqa: E402

RM = Path(run_matrix.__file__)


def check(label, got, want):
    assert got == want, f"{label}: expected {want!r}, got {got!r}"
    print(f"  ok  {label}: {got!r}")


def test_parser_survives_junk():
    t, ev = _parse_stream("123\n", "")
    check("_parse_stream survives bare number", ev, [])
    t, ev = _parse_stream('[1]\n"x"\nnull\n{"type":"assistant","message":null}\n', "")
    check("_parse_stream survives list/str/null/message:null", len(ev), 1)
    check("_iter_tool_uses survives junk", list(_iter_tool_uses([123, None, {"message": None}, {"message": {"content": "x"}}])), [])


def _cli(*args):
    return subprocess.run([sys.executable, str(RM), *args], capture_output=True, text=True)


def _fixture(d):
    d = Path(d)
    for name in ("ok", "_draft/canary/claude-md"):
        (d / "tasks" / name).mkdir(parents=True)
        (d / "tasks" / name / "prompt.md").write_text("hi")
    (d / "configs" / "bare").mkdir(parents=True)
    return ["--tasks-dir", str(d / "tasks"), "--config-dir", str(d / "configs"),
            "--runs-dir", str(d / "runs"), "--ws-root", str(d / "ws"), "--dry-run"]


def test_guards():
    with tempfile.TemporaryDirectory() as d:
        base = _fixture(d)
        r = _cli(*base, "--tasks", "ok", "--layers", "memroy")
        check("unknown layer exits 2", r.returncode, 2)
        assert "memroy" in r.stderr, r.stderr
        r = _cli(*base, "--tasks", "_draft/canary/claude-md", "--layers", "bare")
        check("draft entry exits 2", r.returncode, 2)
        assert "_draft/canary/claude-md" in r.stderr and "promoted out of _draft" in r.stderr, r.stderr
        r = _cli(*base, "--tasks", "ok", "--layers", "bare")
        check("valid plan exits 0", r.returncode, 0)


def test_variant_guards():
    """Knockout variants: four rc-2 preflight refusals, plus the accepted shapes."""
    with tempfile.TemporaryDirectory() as d:
        base = _fixture(d)
        for layer in ("claude-md", "memory", "skills"):
            (Path(d) / "configs" / layer).mkdir()
        (Path(d) / "configs" / "src" / "skills" / "quote").mkdir(parents=True)
        run = lambda layers: _cli(*base, "--tasks", "ok", "--layers", layers)  # noqa: E731
        for label, layers, want in [
            ("unknown mod", "memory,memory~nope", "unknown variant 'nope'"),
            ("nohook on bare", "bare,bare~nohook", "nohook needs a base with the memory hook"),
            ("nohook on claude-md", "claude-md,claude-md~nohook", "nohook needs a base with the memory hook"),
            ("ko of a missing skill", "skills,skills~ko.ghost", "no skill 'ghost'"),
            ("ko on a base without skills", "memory,memory~ko.quote", "ko.<skill> needs a base with skills"),
            ("variant base not in --layers", "bare,memory~nohook", "needs its base 'memory'"),
        ]:
            r = run(layers)
            check(f"{label} exits 2", r.returncode, 2)
            assert want in r.stderr, (label, r.stderr)
        for label, layers in [("nohook", "memory,memory~nohook"), ("ko.quote", "skills,skills~ko.quote")]:
            r = run(layers)
            check(f"{label} plan exits 0", r.returncode, 0)
            assert f"cells=['{layers.split(',')[0]}', '{layers.split(',')[1]}']" in r.stdout, r.stdout


def test_ko_runs_only_on_curated_task():
    check("curated token matches", run_matrix.variant_applies("skills~ko.quote", "quote"), True)
    check("'none (…)' does not match", run_matrix.variant_applies("skills~ko.quote", "none (proves the skills layer loads)"), False)
    check("other skill does not match", run_matrix.variant_applies("full~ko.quote", "dt-qa"), False)
    check("nohook and plain layers always apply",
          [run_matrix.variant_applies(x, "none (x)") for x in ("memory~nohook", "full")], [True, True])


def test_load_rung_missing():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "sha" / "bare").mkdir(parents=True)
        check("existing layer loads", load_rung(Path(d), "bare", "sha"), ({}, []))
        for layer in ("memroy", "full"):
            try:
                load_rung(Path(d), layer, "sha")
            except FileNotFoundError:
                print(f"  ok  load_rung raises for missing layer {layer!r}")
            else:
                raise AssertionError(f"load_rung did not raise for missing layer {layer!r}")


def _run_one(stdout, timed_out=False, info=None, **kw_run):
    import subprocess as sp
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "prompt.md").write_text("hi")
        (d / "configs" / "bare").mkdir(parents=True)

        def fake(cmd, **kw):
            if info is not None:
                info["cmd"] = cmd
            if timed_out:
                raise sp.TimeoutExpired(cmd, 1, output=stdout)
            return types.SimpleNamespace(stdout=stdout, stderr="", returncode=0)

        orig = sp.run
        sp.run = fake
        try:
            out = run_matrix.run_one("t", kw_run.pop("layer", "bare"), "m", d / "tasks", d / "configs", d / "runs",
                                     ws_root=d / "ws", **kw_run)
        finally:
            sp.run = orig
        if info is not None:
            info["name"] = out.name
        tr = out.with_name(out.name.removesuffix(".json") + ".trace.jsonl")
        return json.loads(out.read_text()), (tr.read_text() if tr.exists() else "")


def test_meta_no_result_and_trace():
    ev = '{"type":"assistant","message":{"usage":{"output_tokens":3}}}\n'
    res = '{"type":"result","is_error":false,"result":"ok","usage":{"output_tokens":3}}\n'
    t, _ = _run_one(ev)
    check("no result event -> no_result True", t["_meta"]["no_result"], True)
    t, trace = _run_one(ev + res)
    check("result event -> no_result False", t["_meta"]["no_result"], False)
    check("trace has no _meta", "_meta" in trace, False)
    check("trace keeps result event", '"type": "result"' in trace, True)
    t, _ = _run_one(ev, timed_out=True)
    check("timeout -> no_result False", t["_meta"]["no_result"], False)


def _fake_security(d, code, marker):
    """A `security` on PATH that records the call and exits `code` (44 = item not found)."""
    bin_ = Path(d) / "bin"
    bin_.mkdir()
    (bin_ / "security").write_text(f"#!/bin/sh\necho called >> {marker}\n"
                                   f"{'echo fake-token' if code == 0 else ''}\nexit {code}\n")
    (bin_ / "security").chmod(0o755)
    return str(bin_)


def test_token_keychain():
    import os
    with tempfile.TemporaryDirectory() as d:
        marker = Path(d) / "calls"
        bin_ = _fake_security(d, 44, marker)
        base = _fixture(d)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_OAUTH_TOKEN"}
        env["PATH"] = f"{bin_}:{os.environ['PATH']}"

        def cli(*a, **extra):
            return subprocess.run([sys.executable, str(RM), *a], capture_output=True, text=True, env={**env, **extra})

        r = cli(*base, "--tasks", "ok", "--layers", "bare")
        check("dry-run needs no keychain", (r.returncode, marker.exists()), (0, False))
        live = [a for a in base if a != "--dry-run"]
        r = cli(*live, "--tasks", "ok", "--layers", "bare")
        check("missing keychain item exits 2", r.returncode, 2)
        assert "os-evals-claude-token" in r.stderr and "security add-generic-password" in r.stderr, r.stderr
        check("keychain was asked", marker.exists(), True)
        check("no run dir made before failing", (Path(d) / "ws").exists(), False)

        # env override: the keychain is never consulted
        marker.unlink()
        run_matrix._TOKEN = None
        old = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"), os.environ["PATH"]
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"], os.environ["PATH"] = "from-env", env["PATH"]
        try:
            check("env override wins", run_matrix.oauth_token(), "from-env")
            check("env override skips keychain", marker.exists(), False)
            # no override + working keychain: read once, cached
            del os.environ["CLAUDE_CODE_OAUTH_TOKEN"]
            run_matrix._TOKEN = None
            (Path(bin_) / "security").write_text(f"#!/bin/sh\necho called >> {marker}\necho kc-token\n")
            check("keychain read", run_matrix.oauth_token(), "kc-token")
            run_matrix.oauth_token()
            check("keychain read once per process", marker.read_text().count("called"), 1)
        finally:
            run_matrix._TOKEN = None
            os.environ["PATH"] = old[1]
            if old[0] is not None:
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = old[0]


def test_token_injected():
    import subprocess as sp
    seen = {}
    for layer in ("bare", "full"):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "tasks" / "t").mkdir(parents=True)
            (d / "tasks" / "t" / "prompt.md").write_text("hi")
            (d / "configs" / layer).mkdir(parents=True)
            (d / "configs" / layer / "rung.env").write_text("HOME=/h\n")

            def fake(cmd, **kw):
                seen[layer] = kw["env"]
                return types.SimpleNamespace(stdout="", stderr="", returncode=0)

            orig, run_matrix._TOKEN, sp.run = sp.run, "tok-123", fake
            try:
                run_matrix.run_one("t", layer, "m", d / "tasks", d / "configs", d / "runs", ws_root=d / "ws")
            finally:
                sp.run, run_matrix._TOKEN = orig, None
    check("full gets OAuth name only", (seen["full"].get("CLAUDE_CODE_OAUTH_TOKEN"), "ANTHROPIC_AUTH_TOKEN" in seen["full"]),
          ("tok-123", False))
    check("bare gets both names", (seen["bare"].get("CLAUDE_CODE_OAUTH_TOKEN"), seen["bare"].get("ANTHROPIC_AUTH_TOKEN")),
          ("tok-123", "tok-123"))
    check("rung.env HOME kept", seen["full"]["HOME"], "/h")


def test_pre18_snapshot():
    old = '{"h": "bash -c \'set -a; . \\"$CLAUDE_CONFIG_DIR/rung.env\\"; set +a; exec python3 /s/scripts/memory-relevance-hook.py\'"}'
    cur = old.replace("exec", "t=$(security find-generic-password -s os-evals-claude-token -w); exec")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for name, text in (("old", old), ("cur", cur), ("nohook", '{"autoMemoryEnabled": false}')):
            (d / "configs" / name / "memory").mkdir(parents=True)  # configs/<sha>/<layer>
            (d / "configs" / name / "memory" / "settings.json").write_text(text)
        t = lambda n: run_matrix.is_pre18_snapshot(d / "configs" / n / "memory")  # noqa: E731
        check("old wrapper flagged", t("old"), True)
        check("current wrapper / no hook / no settings.json pass", [t("cur"), t("nohook"), t("absent")], [False] * 3)
        (d / "tasks" / "ok").mkdir(parents=True)
        (d / "tasks" / "ok" / "prompt.md").write_text("hi")
        argv = ["--tasks-dir", str(d / "tasks"), "--config-dir", str(d / "configs"), "--runs-dir", str(d / "runs"),
                "--ws-root", str(d / "ws"), "--tasks", "ok", "--layers", "memory", "--models", "m", "--os-sha", "old"]
        (d / "bin").mkdir()  # guard rail: if the refusal ever regresses, the "claude" that runs is this stub
        (d / "bin" / "claude").write_text("#!/bin/sh\nexit 1\n")
        (d / "bin" / "claude").chmod(0o755)
        env = {**os.environ, "PATH": f"{d / 'bin'}:{os.environ['PATH']}", "CLAUDE_CODE_OAUTH_TOKEN": "dummy"}
        r = subprocess.run([sys.executable, str(RM), *argv], capture_output=True, text=True, env=env)  # real path
        check("real run on old snapshot exits 2", r.returncode, 2)
        assert "pre-1.8 snapshot" in r.stderr, r.stderr
        r = _cli(*argv, "--dry-run")
        check("dry run on old snapshot warns, exits 0", (r.returncode, "WARNING pre-1.8" in r.stdout), (0, True))


def test_variant_meta():
    res = '{"type":"result","is_error":false,"result":"ok","usage":{"output_tokens":3}}\n'
    info = {}
    t, _ = _run_one(res, info=info, layer="bare~nohook")
    m = t["_meta"]
    check("_meta layer=base, variant, rung=full spec", (m["layer"], m["variant"], m["rung"]), ("bare", "nohook", "bare~nohook"))
    check("run id embeds the full spec", "_bare~nohook_m_high.json" in info["name"], True)
    t, _ = _run_one(res)
    check("plain layer: variant empty", (t["_meta"]["layer"], t["_meta"]["variant"], t["_meta"]["rung"]), ("bare", "", "bare"))


def test_effort_in_run_id_and_meta():
    init = '{"type":"system","subtype":"init","model":"claude-haiku-9-9"}\n'
    res = '{"type":"result","is_error":false,"result":"ok","usage":{"output_tokens":3}}\n'
    info = {}
    t, _ = _run_one(init + res, info=info, effort="xhigh")
    check("run file name ends _m_xhigh.json", info["name"].endswith("_bare_m_xhigh.json"), True)
    check("cmd carries --effort xhigh", info["cmd"][info["cmd"].index("--effort") + 1], "xhigh")
    check("_meta.effort", t["_meta"]["effort"], "xhigh")
    check("_meta.model_resolved from init event", t["_meta"]["model_resolved"], "claude-haiku-9-9")
    info = {}
    t, _ = _run_one(res, info=info)
    check("default effort high in name", info["name"].endswith("_bare_m_high.json"), True)
    check("no init event -> model_resolved None", t["_meta"]["model_resolved"], None)


def test_task_budget_override_and_passthrough():
    with tempfile.TemporaryDirectory() as d:
        t = Path(d) / "t"
        t.mkdir()
        (t / "meta.yaml").write_text(
            "max_budget_usd: 6  # C1\nlayer_neutral: true\nsignals: a,b  # non-gating\n"
            'judge_files: "src/x.mjs,test/*.test.mjs"\ndescription: |\n  max_budget_usd: 99\n  layer_neutral: false\n')
        m = run_matrix.read_task_meta(t)
        check("max_budget_usd parsed, indented prose ignored", m["max_budget_usd"], 6.0)
        check("layer_neutral parsed", m["layer_neutral"], True)
        check("signals passed through, comment stripped", m["signals"], "a,b")
        check("judge_files passed through, quotes stripped", m["judge_files"], "src/x.mjs,test/*.test.mjs")
        check("defaults when absent", run_matrix.read_task_meta(Path(d) / "none")["max_budget_usd"], None)
    cap = lambda cmd: cmd[cmd.index("--max-budget-usd") + 1]  # noqa: E731
    check("explicit CLI cap beats meta", cap(run_matrix.build_cmd("m", [], {"max_budget_usd": 6.0}, 0.5)), "0.5")
    check("meta cap applies when no CLI cap", cap(run_matrix.build_cmd("m", [], {"max_budget_usd": 6.0}, None)), "6.0")
    check("no CLI cap, no meta -> 1.50", cap(run_matrix.build_cmd("m", [], {"max_budget_usd": None}, None)), "1.5")
    info = {}
    _run_one('{"type":"result","is_error":false,"result":"ok"}\n', info=info)
    check("run_one with neither cap -> 1.50", cap(info["cmd"]), "1.5")


def test_budget_dry_run_effective_cap():
    with tempfile.TemporaryDirectory() as d:
        base = _fixture(d)
        (Path(d) / "tasks" / "big").mkdir()
        (Path(d) / "tasks" / "big" / "prompt.md").write_text("hi")
        (Path(d) / "tasks" / "big" / "meta.yaml").write_text("max_budget_usd: 6\n")
        out = _cli(*base, "--tasks", "ok,big", "--layers", "bare").stdout
        check("no CLI cap: command line shows the 1.5 default", "--max-budget-usd 1.5 " in out, True)
        check("no CLI cap: meta task listed with its cap", "max_budget_usd: big \u2014 6.0 (meta.yaml)" in out, True)
        check("no CLI cap: plain task not listed", "max_budget_usd: ok" in out, False)
        out = _cli(*base, "--tasks", "ok,big", "--layers", "bare", "--max-budget-usd", "0.5").stdout
        check("explicit CLI cap shown", "--max-budget-usd 0.5 " in out, True)
        check("explicit CLI cap: meta not listed (it loses)", "max_budget_usd: big" in out, False)


def test_skill_fired_agent_and_one_shot():
    ev = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Agent", "input": {"subagent_type": "dt-engineer", "description": "x"}}]}}]
    check("Agent spawn naming the skill counts", run_matrix.detect_skill_fired(ev, "dt-engineer"), True)
    check("Task spawn still counts", run_matrix.detect_skill_fired(
        [{"message": {"content": [{"type": "tool_use", "name": "Task", "input": {"subagent_type": "dt-qa"}}]}}], "dt-qa"), True)
    check("no match -> False", run_matrix.detect_skill_fired(ev, "ponytail"), False)
    check("no curated skill -> None", run_matrix.detect_skill_fired(ev, ""), None)
    # one-shot (multi_turn false) run with a curated_skill still gets skill_fired computed
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tasks" / "t").mkdir(parents=True)
        (d / "tasks" / "t" / "prompt.md").write_text("hi")
        (d / "tasks" / "t" / "meta.yaml").write_text("curated_skill: dt-engineer\nlayer_neutral: true\n")
        (d / "configs" / "bare").mkdir(parents=True)
        out = json.dumps(ev[0]) + '\n{"type":"result","is_error":false,"result":"ok"}\n'
        import subprocess as sp
        orig = sp.run
        sp.run = lambda cmd, **kw: types.SimpleNamespace(stdout=out, stderr="", returncode=0)
        try:
            f = run_matrix.run_one("t", "bare", "m", d / "tasks", d / "configs", d / "runs", ws_root=d / "ws")
        finally:
            sp.run = orig
        meta = json.loads(f.read_text())["_meta"]
        check("one-shot run: skill_fired computed", (meta["multi_turn"], meta["skill_fired"]), (False, True))
        check("_meta.layer_neutral", meta["layer_neutral"], True)


def test_arm_variant_guards():
    """skills~trigger / skills~forced[.<skill>]: accepted shapes, rc 2 refusals, skip rules."""
    with tempfile.TemporaryDirectory() as d:
        base = _fixture(d)
        for layer in ("memory", "skills"):
            (Path(d) / "configs" / layer).mkdir()
        (Path(d) / "configs" / "src" / "skills" / "quote").mkdir(parents=True)
        (Path(d) / "tasks" / "ok" / "meta.yaml").write_text("curated_skill: none (no skill here)\n")
        (Path(d) / "tasks" / "curated").mkdir()
        (Path(d) / "tasks" / "curated" / "prompt.md").write_text("hi")
        (Path(d) / "tasks" / "curated" / "meta.yaml").write_text("curated_skill: quote\n")
        (Path(d) / "tasks" / "trig").mkdir()
        (Path(d) / "tasks" / "trig" / "prompt.md").write_text("hi")
        (Path(d) / "tasks" / "trig" / "meta.yaml").write_text('curated_skill: quote\ntrigger: "quote this:"\n')
        run = lambda tasks, layers: _cli(*base, "--tasks", tasks, "--layers", layers)  # noqa: E731
        r = run("ok", "skills,skills~forced")
        check("forced with curated_skill none: skipped with a notice, rc 0 (was rc 2 before the skip-not-abort rule)", r.returncode, 0)
        assert "skills~forced: ok \u2014 skipped (needs a curated_skill)" in r.stdout, r.stdout
        r = run("curated", "skills,skills~forced.nosuchskill")
        check("forced.nosuchskill exits 2", r.returncode, 2)
        assert "no skill 'nosuchskill'" in r.stderr, r.stderr
        r = run("curated", "memory,memory~forced")
        check("forced on a base without skills exits 2", r.returncode, 2)
        assert "forced needs a base with skills" in r.stderr, r.stderr
        r = run("curated", "skills,skills~trigger,skills~forced")
        check("trigger+forced plan exits 0", r.returncode, 0)
        assert "skills~trigger: curated \u2014 skipped (needs a `trigger`" in r.stdout, r.stdout
        assert "curated: 2 cells" in r.stdout and "'skills~forced'" in r.stdout, r.stdout
        r = run("trig", "skills,skills~trigger,skills~forced")
        check("task with trigger meta plans all 3 cells", "trig: 3 cells" in r.stdout, True)
        r = run("ok", "skills,skills~forced.quote")
        check("explicit forced.<skill> overrides a none task", (r.returncode, "ok: 2 cells" in r.stdout), (0, True))


def test_arm_applies_and_prompt():
    va = run_matrix.variant_applies
    check("trigger needs trigger + real skill", [va("skills~trigger", "quote", "x"), va("skills~trigger", "quote", ""),
                                                 va("skills~trigger", "none (x)", "x")], [True, False, False])
    check("forced needs real skill or explicit one", [va("full~forced", "quote"), va("full~forced", "none (x)"), va("full~forced", ""),
                                                     va("full~forced.quote", "none (x)")], [True, False, False, True])
    check("ko unchanged", va("skills~ko.quote", "none (x)"), False)
    meta = {"curated_skill": "dev-team (x)", "trigger": "humanize this:", "forced_note": "", "tools": "read"}
    check("trigger prompt", run_matrix.arm_prompt("BODY\n", "trigger", meta), ("humanize this:\n\nBODY\n", "trigger", ""))
    check("forced prompt uses the first curated token", run_matrix.arm_prompt("BODY", "forced", meta), ("/dev-team BODY", "forced", "dev-team"))
    check("forced.<skill> overrides", run_matrix.arm_prompt("BODY", "forced.other", meta), ("/other BODY", "forced", "other"))
    check("forced_note appended after a blank line",
          run_matrix.arm_prompt("BODY", "forced", {**meta, "forced_note": "Be brief."})[0], "/dev-team BODY\n\nBe brief.")
    check("other mods leave the prompt alone", run_matrix.arm_prompt("BODY", "nohook", meta), ("BODY", "", ""))
    check("plain layer", run_matrix.arm_prompt("BODY", "", meta), ("BODY", "", ""))


def test_tools_read_flag_and_meta_strings():
    cmd = run_matrix.build_cmd("m", [], {"tools": "read"})
    check("tools: read -> Skill,Read,Glob,Grep", cmd[cmd.index("--tools") + 1], "Skill,Read,Glob,Grep")
    check("tools: none still empty", run_matrix.build_cmd("m", [], {"tools": "none"})[run_matrix.build_cmd("m", [], {"tools": "none"}).index("--tools") + 1], "")
    check("no tools meta: no --tools flag", "--tools" in run_matrix.build_cmd("m", [], {"tools": ""}), False)
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t / "meta.yaml").write_text('tools: read\ntrigger: "humanize this:"  # note\nforced_note: "Reply only."\n'
                                     'description: |\n  trigger: "indented prose"\n')
        m = run_matrix.read_task_meta(t)
        check("tools/trigger/forced_note parsed, quotes + comment stripped, indented ignored",
              (m["tools"], m["trigger"], m["forced_note"]), ("read", "humanize this:", "Reply only."))
        check("absent -> empty", run_matrix.read_task_meta(t / "nope")["trigger"], "")


def test_arm_run_one_stdin_and_meta():
    res = '{"type":"result","is_error":false,"result":"ok"}\n'
    for layer, want_stdin, want_arm in [("skills~forced", "/humanizer BODY\n\nNOTE", "forced"),
                                        ("skills~forced.other", "/other BODY\n\nNOTE", "forced"),
                                        ("skills~trigger", "do it:\n\nBODY", "trigger")]:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "tasks" / "t").mkdir(parents=True)
            (d / "tasks" / "t" / "prompt.md").write_text("BODY")
            (d / "tasks" / "t" / "meta.yaml").write_text('curated_skill: humanizer\ntrigger: "do it:"\nforced_note: "NOTE"\n')
            (d / "configs" / "skills").mkdir(parents=True)
            seen = {}
            import subprocess as sp
            orig = sp.run

            def fake(cmd, **kw):
                seen["input"] = kw.get("input")
                return types.SimpleNamespace(stdout=res, stderr="", returncode=0)
            sp.run = fake
            try:
                f = run_matrix.run_one("t", layer, "m", d / "tasks", d / "configs", d / "runs", ws_root=d / "ws")
            finally:
                sp.run = orig
            meta = json.loads(f.read_text())["_meta"]
        check(f"{layer}: stdin", seen["input"], want_stdin)
        check(f"{layer}: _meta arm/forced_skill/rung", (meta["arm"], meta["forced_skill"], meta["rung"], meta["variant"]),
              (want_arm, {"skills~forced": "humanizer", "skills~forced.other": "other"}.get(layer, ""), layer, layer.split("~")[1]))
        check(f"{layer}: skill_fired", meta["skill_fired"], True if want_arm == "forced" else False)


def test_layer_neutral_bare_only_dry_run():
    with tempfile.TemporaryDirectory() as d:
        base = _fixture(d)
        (Path(d) / "configs" / "full").mkdir()
        for name, meta in (("ln", "layer_neutral: true\n"), ("sent", "sentinel: true\n"), ("ok", "")):
            (Path(d) / "tasks" / name).mkdir(exist_ok=True)
            (Path(d) / "tasks" / name / "prompt.md").write_text("hi")
            (Path(d) / "tasks" / name / "meta.yaml").write_text(meta)
        r = _cli(*base, "--tasks", "ln,sent,ok", "--layers", "bare,full")
        check("exit 0", r.returncode, 0)
        out = r.stdout
        check("layer_neutral listed on bare only", "layer_neutral: ln \u2014 bare layer only" in out, True)
        check("ln plans 1 cell", "  ln: 1 cells" in out, True)
        check("sentinel still bare only", "sentinel: sent \u2014 bare layer only" in out and "  sent: 1 cells" in out, True)
        check("normal task keeps both cells", "  ok: 2 cells" in out, True)
        out = _cli(*base, "--tasks", "ln,ok", "--layers", "full").stdout
        check("layer_neutral with bare excluded says skipped", "layer_neutral: ln \u2014 skipped (0 cells, bare not in --layers)" in out, True)
        check("...and plans 0 cells", "  ln: 0 cells" in out, True)


if __name__ == "__main__":
    test_task_budget_override_and_passthrough()
    test_budget_dry_run_effective_cap()
    test_skill_fired_agent_and_one_shot()
    test_layer_neutral_bare_only_dry_run()
    test_arm_variant_guards()
    test_arm_applies_and_prompt()
    test_tools_read_flag_and_meta_strings()
    test_arm_run_one_stdin_and_meta()
    test_parser_survives_junk()
    test_guards()
    test_variant_guards()
    test_ko_runs_only_on_curated_task()
    test_load_rung_missing()
    test_variant_meta()
    test_meta_no_result_and_trace()
    test_token_keychain()
    test_token_injected()
    test_pre18_snapshot()
    test_effort_in_run_id_and_meta()
    print("ALL PASS")
