#!/usr/bin/env bash
# Present the consumer incident using the traceable fault runner.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 scripts/verify-pipeline.py
exec python3 scripts/failure-suite.py consumer
