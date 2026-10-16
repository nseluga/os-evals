"""Stream-json trace helpers for check.sh scripts (stdlib). Use from a check via
`sys.path.insert(0, "<repo>/harness"); import trace_lib` or `python3 -c`.

Only `assistant` events' message.content blocks are scanned, never tool_result payloads
(they echo tool_use dicts back). `Agent` and `Task` are the same spawn tool. Real
stream-json has one tool_use per line; parallel calls share message.id across lines, so
msg_index (order of first appearance of message.id) is the turn, not the line.
"""
import json


def events(path):
    out = []
    with open(path) as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict):
                out.append(ev)
    return out


def _blocks(evs):
    """Yield (event, msg_id, msg_index, block) for tool_use blocks in assistant events."""
    turn = {}
    for i, ev in enumerate(evs):
        if ev.get("type") != "assistant":
            continue
        msg = ev.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        mid = msg.get("id") or f"line{i}"
        turn.setdefault(mid, len(turn))
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                yield ev, mid, turn[mid], b


def tool_uses(evs):
    """[(name, input, parent_tool_use_id)] -- parent id is set on subagent-side events."""
    return [(b.get("name", ""), b.get("input") or {}, ev.get("parent_tool_use_id"))
            for ev, _, _, b in _blocks(evs)]


def spawns(evs):
    """[(subagent_type, model, description, prompt, msg_id, msg_index)] for Agent/Task calls."""
    return [(str(i.get("subagent_type") or ""), str(i.get("model") or ""), str(i.get("description") or ""),
             str(i.get("prompt") or ""), mid, idx)
            for _, mid, idx, b in _blocks(evs) if b.get("name") in ("Agent", "Task")
            for i in [b.get("input") or {}]]


def bash_cmds(evs):
    return [str(i.get("command", "")) for n, i, _ in tool_uses(evs) if n == "Bash"]


def skill_calls(evs):
    """[(skill, args)] for Skill tool calls."""
    return [(str(i.get("skill") or i.get("command") or ""), str(i.get("args") or ""))
            for n, i, _ in tool_uses(evs) if n == "Skill"]
