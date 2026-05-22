#!/bin/bash
# Script de inicio para Gestión de Tickets - CEDIR
# Uso: ./run.sh

DIR="$(cd "$(dirname "$0")" && pwd)"

# Crear directorio de logs si no existe
mkdir -p "$DIR/logs"

# Activar el entorno virtual
. "$DIR/venv/bin/activate"

# Iniciar Gunicorn
exec gunicorn \
    -w 2 \
    -k gthread \
    --threads 4 \
    --timeout 180 \
    -b 0.0.0.0:5151 \
    --limit-request-line 8190 \
    --limit-request-field_size 8190 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile "$DIR/logs/access.log" \
    --error-logfile "$DIR/logs/error.log" \
    --log-level info \
    wsgi:app
