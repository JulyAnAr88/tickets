#!/bin/bash
# Script de inicio para Gestión de Tickets - CEDIR
# Uso: ./run.sh

DIR="$(cd "$(dirname "$0")" && pwd)"

# Cargar .env para tener LOG_DIR y otras variables
set -a
. "$DIR/.env" 2>/dev/null || true
set +a

# Directorio de logs: LOG_DIR del .env o default
LOG_DIR="${LOG_DIR:-$DIR/logs}"
mkdir -p "$LOG_DIR"

# Activar el entorno virtual
. "$DIR/venv/bin/activate"

# Iniciar Gunicorn

exec gunicorn \
    -c "$DIR/gunicorn_config.py" \
    wsgi:application
