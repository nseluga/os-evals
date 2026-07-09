#!/bin/bash
set -euo pipefail
# Provision a minimal Python env for the property-based ACWR check. The check only
# needs pandas + numpy (synthetic input; no Statcast data). Creates .venv in the
# restored workspace; check.sh picks it up via PYTHON_BIN.
python3 -m venv .venv
./.venv/bin/pip install --quiet --disable-pip-version-check pandas numpy
