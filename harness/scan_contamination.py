#!/usr/bin/env python3
"""
harness/scan_contamination.py [DIR]

Report-only scan of stored traces (default runs/; pass runs/archive/<ts> for archives).
For each *.trace.jsonl, applies contamination.find_contamination with the bare rule set
(strictest) unless the matching transcript's _meta names the layer (new runs), in which
case that layer's rules apply. Old runs have an int `rung`: 1 is bare; 2-4 had no
snapshot, so live ~/os reads are hits there too and get their own column.
Exit 0 always.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from contamination import contamination_rules, find_contamination  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent


def scan_trace(trace: Path, repo: Path = REPO_ROOT, home: Path | None = None):
    """(label, hits, live_os_hits) for one trace file."""
    home = home or Path.home()
    events = []
    for line in trace.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    tf = trace.with_name(trace.name.removesuffix(".trace.jsonl") + ".json")
    try:
        meta = json.loads(tf.read_text()).get("_meta", {})
    except (OSError, ValueError):
        meta = {}
    ws = meta.get("workspace_dir") or next(
        (e.get("cwd", "") for e in events if e.get("type") == "system" and e.get("subtype") == "init"), "")
    task_dir = repo / "tasks" / (meta.get("task") or "")
    layer = meta.get("layer")
    label = str(layer) if layer else f"rung{meta.get('rung', '?')}"
    if layer:
        forbidden, allowed, tilde = contamination_rules(
            repo, home, repo / "configs", task_dir, layer, meta.get("os_sha", ""), ws,
            bool(meta.get("home_isolated")), ws_root=str(Path(ws).parent) if ws else None)
    else:  # old run: strictest (bare) rules
        forbidden, allowed, tilde = contamination_rules(repo, home, repo / "configs", task_dir, "bare", "", ws, False,
                                                     ws_root=str(Path(ws).parent) if ws else None)
    hits = find_contamination(events, forbidden, allowed, tilde)
    live = [str(home / d) for d in ("os", "personal-os")]
    live_hits = find_contamination(events, live, [ws], str(home))
    return label, hits, live_hits


def main() -> int:
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "runs"
    rows = [("run id", "rung/layer", "hits", "live-os", "first hit")]
    for t in sorted(d.glob("*.trace.jsonl")):
        label, hits, live = scan_trace(t)
        rows.append((t.name.removesuffix(".trace.jsonl"), label, str(len(hits)), str(len(live)),
                     hits[0].replace("\n", " ")[:100] if hits else ""))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r[:4], widths)) + "  " + r[4])
    print(f"scanned {len(rows) - 1} traces in {d}; contaminated {sum(1 for r in rows[1:] if r[2] != '0')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
