#!/bin/bash
# Builds a tiny git working copy in $PWD: main with 1 commit, branch feat/retry-backoff with 1 more.
# The origin URL is fake, so no network call can succeed.
set -euo pipefail
git init -q -b main
git config user.name "Eval Fixture"
git config user.email "fixture@example.invalid"
git add README.md crewlog.py
git commit -q -m "Initial crewlog"
git checkout -q -b feat/retry-backoff
git add retry.py
git commit -q -m "Add retry backoff helper"
git checkout -q main
git remote add origin https://github.com/example-org/crewlog.git
