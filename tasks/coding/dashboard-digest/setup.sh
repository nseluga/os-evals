#!/bin/bash
set -euo pipefail
# Provision JS deps for the restored dashboard workspace so vitest is available.
# Runs in the restored workspace (cwd). node_modules is deliberately not in the archive.
npm ci --no-audit --no-fund
