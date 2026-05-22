import os
from pathlib import Path

# Directorio de logs configurable (LOG_DIR en .env o default junto al config)
_log_dir = os.environ.get('LOG_DIR', str(Path(__file__).parent / 'logs'))

bind = '0.0.0.0:5151'
workers = 1
worker_class = 'sync'
timeout = 300
keepalive = 5
max_requests = 500
max_requests_jitter = 50
accesslog = f'{_log_dir}/access.log'
errorlog = f'{_log_dir}/error.log'
loglevel = 'info'
capture_output = True

def on_starting(server):
    """Inicializar DB al arrancar el servidor"""
    from app import init_db
    init_db()
