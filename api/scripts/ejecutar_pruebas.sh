#!/usr/bin/env bash
# Corre los tests (no requieren bases: validan contrato y manejo de errores).
set -e
cd "$(dirname "$0")/.."
python -m pytest tests/ -v
