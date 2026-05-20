import os
import sys
from pathlib import Path

# Agregar el directorio del proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

from app import app, db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)

if __name__ != '__main__':
    # En producción (gunicorn), ejecutar setup al iniciar
    with app.app_context():
        esquema = app.config.get('DB_SCHEMA', 'cedir')
        print(f"🔧 Usando esquema de base de datos: {esquema}")
        db.session.execute(text(f"SET search_path TO {esquema}"))
        db.create_all()
        print("✅ Base de datos inicializada")
