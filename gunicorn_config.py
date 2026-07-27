import os
from pathlib import Path

# Directorio de logs configurable (LOG_DIR en .env o default junto al config)
_log_dir = os.environ.get('LOG_DIR', str(Path(__file__).parent / 'logs'))

bind = '0.0.0.0:5001'
workers = 2
worker_class = 'sync'
timeout = 180
keepalive = 5
max_requests = 1000
max_requests_jitter = 200
max_requests_during_restart = 10
accesslog = f'{_log_dir}/access.log'
errorlog = f'{_log_dir}/error.log'
loglevel = 'info'
capture_output = True

def on_starting(server):
    """Inicializar DB al arrancar el servidor"""
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('gunicorn.startup')
    try:
        from app import init_db
        init_db()
        logger.info("✅ Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"⚠️ Error inicializando base de datos: {e}. El servidor igualmente arrancará.")
