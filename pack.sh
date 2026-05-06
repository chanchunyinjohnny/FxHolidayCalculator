#!/usr/bin/env bash
set -euo pipefail

rm -rf dist build *.egg-info
python -m build
ls -lh dist/
