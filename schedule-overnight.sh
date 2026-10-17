#!/bin/bash
set -euo pipefail
# schedule-overnight.sh: point the launchd job com.bcns.os-evals-overnight at one night (fires once at 03:00
# local time on the given date; if the Mac is asleep, launchd runs it on wake) in one overnight.sh MODE.
# Refuses while a matrix is running. Rewrites ~/Library/LaunchAgents/com.bcns.os-evals-overnight.plist and reloads it.
#
# Usage: ./schedule-overnight.sh 2026-10-17 skill-lift
#        ./schedule-overnight.sh 2026-10-18 skill-opus
#        ./schedule-overnight.sh 2026-10-19 orchestrate
#        ./schedule-overnight.sh --show          # print the scheduled date/mode and launchctl status

LABEL=com.bcns.os-evals-overnight
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "${1:-}" = "--show" ]; then
    [ -f "$PLIST" ] || { echo "no plist at $PLIST"; exit 1; }
    python3 - "$PLIST" <<'PY'
import plistlib, sys
d = plistlib.load(open(sys.argv[1], "rb")); c = d["StartCalendarInterval"]
e = d["EnvironmentVariables"]
print(f"plist: {e.get('RUN_DATE', '????')} ({c['Month']:02d}-{c['Day']:02d}) {c['Hour']:02d}:{c['Minute']:02d} mode={e.get('MODE','(unset -> skill-lift)')}")
PY
    # What launchd actually loaded (the file can be newer than the job if a reload failed).
    launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -E 'MODE|RUN_DATE|Day|Hour|state' | sed 's/^/loaded: /' \
        || echo "launchctl: job not loaded"
    exit 0
fi

DATE="${1:?usage: schedule-overnight.sh YYYY-MM-DD skill-lift|skill-opus|orchestrate|round3}"
MODE="${2:?usage: schedule-overnight.sh YYYY-MM-DD skill-lift|skill-opus|orchestrate|round3}"
case "$MODE" in skill-lift|skill-opus|orchestrate|round3) ;; *) echo "unknown mode $MODE" >&2; exit 2;; esac
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "date must be YYYY-MM-DD" >&2; exit 2; }
date -j -f %Y-%m-%d "$DATE" +%s >/dev/null 2>&1 || { echo "not a real date: $DATE" >&2; exit 2; }
[ "$DATE" \> "$(date +%Y-%m-%d)" ] || { echo "date must be after today ($(date +%Y-%m-%d)): $DATE" >&2; exit 2; }
MONTH=$((10#${DATE:5:2})); DAY=$((10#${DATE:8:2}))
# Anchored so an editor or shell whose command line merely mentions these files does not count as a run.
if pgrep -f '^(/[^ ]*/)?(python[0-9.]* [^ ]*harness/run_matrix\.py|bash [^ ]*overnight\.sh)' >/dev/null; then
    echo "a matrix is running (pgrep run_matrix/overnight.sh); not touching launchd" >&2; exit 1
fi

python3 - "$PLIST" "$LABEL" "$SCRIPT_DIR" "$MONTH" "$DAY" "$MODE" "$DATE" <<'PY'
import plistlib, sys, os
plist, label, root, month, day, mode, run_date = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), sys.argv[6], sys.argv[7]
d = {
    "Label": label,
    "ProgramArguments": ["/bin/bash", f"{root}/overnight.sh"],
    "WorkingDirectory": root,
    "StartCalendarInterval": {"Month": month, "Day": day, "Hour": 3, "Minute": 0},
    "EnvironmentVariables": {
        "PATH": f"{os.environ['HOME']}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "MODE": mode,
        "RUN_DATE": run_date,  # overnight.sh exits unless today matches (StartCalendarInterval has no Year)
    },
    "StandardOutPath": f"{root}/overnight-logs/launchd.out",
    "StandardErrorPath": f"{root}/overnight-logs/launchd.err",
}
os.makedirs(os.path.dirname(plist), exist_ok=True)
with open(plist, "wb") as f: plistlib.dump(d, f)
PY
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
# bootout is asynchronous; bootstrap right after it can fail with "5: Input/output error". Retry briefly.
for i in 1 2 3 4 5; do
    launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null && break
    [ "$i" -eq 5 ] && { echo "launchctl bootstrap failed 5 times; plist written but NOT loaded: $PLIST" >&2; exit 1; }
    sleep 1
done
echo "scheduled $LABEL: $DATE 03:00 local, MODE=$MODE"
launchctl print "gui/$(id -u)/$LABEL" | grep -E 'MODE|RUN_DATE' | sed 's/^/loaded: /'
