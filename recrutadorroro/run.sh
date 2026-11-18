#!/usr/bin/env bash
# Instala as dependências (na primeira vez) e abre o RecrutadorRORO em http://127.0.0.1:8000
# Uso: ./run.sh            PORTA=9000 ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

PORTA="${PORTA:-8000}"
PY="${PYTHON:-python3}"

if [[ ! -d .venv ]]; then
  echo "→ criando ambiente Python (.venv)"
  "$PY" -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

echo "→ RecrutadorRORO em http://127.0.0.1:${PORTA}  (Ctrl+C para parar)"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORTA"
