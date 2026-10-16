#!/bin/bash
set -euo pipefail
P=com.nateseluga.project-dashboard.plist
launchctl unload ~/Library/LaunchAgents/$P || true
rm -f ~/Library/LaunchAgents/$P
