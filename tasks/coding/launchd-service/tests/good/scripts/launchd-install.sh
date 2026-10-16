#!/bin/bash
set -euo pipefail
P=com.nateseluga.project-dashboard.plist
cp "$P" ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/$P
echo "Dashboard service installed. Visit http://localhost:4321"
