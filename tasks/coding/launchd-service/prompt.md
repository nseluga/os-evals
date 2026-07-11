I want to run my project dashboard as a persistent macOS background service using launchd, so localhost:4321 is always available without manually running npm run dev.

Project location: (this repository — the current working directory)
Start command: npm run dev (runs astro dev, which starts on port 4321)
Node location: find it with `which node` — use the absolute path in the plist, not npm via PATH, since launchd has a minimal environment.

What to build:

1. A launchd plist at `com.nateseluga.project-dashboard.plist` in the repo root that:
  - Runs on login (RunAtLoad: true)
  - Keeps the process alive if it exits (KeepAlive: true)
  - Logs stdout to /tmp/project-dashboard.log and stderr to /tmp/project-dashboard.err
  - Sets WorkingDirectory to the project directory
  - Uses the absolute path to node and node_modules/.bin/astro — NOT `npm run dev`, which requires PATH to find npm
2. A short `scripts/launchd-install.sh` in the project that:
  - Copies the plist to ~/Library/LaunchAgents/
  - Runs `launchctl load -w ~/Library/LaunchAgents/com.nateseluga.project-dashboard.plist`
  - Prints a confirmation like "Dashboard service installed. Visit http://localhost:4321"
3. A matching `scripts/launchd-uninstall.sh` that unloads and removes the plist.

Important: Use `node <abs-project-path>/node_modules/.bin/astro dev` as the actual ProgramArguments command (not `npm run dev`), because launchd won't have the right PATH to find npm. Confirm the node path with `which node` and use that exact path.

After writing the files, make the two scripts executable.
