import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'tu-clave-secreta-aqui'
    
    # Configuración de PostgreSQL
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME', 'tu_base_datos')
    DB_USER = os.environ.get('DB_USER', 'tu_usuario')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'tu_contraseña')
    
    SQLALCHEMY_DATABASE_URI = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuración de uploads (para imágenes)
    # UPLOAD_FOLDER = 'static/uploads'
    # PROCESSED_FOLDER = 'static/processed'
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', '/home/files/incoming')
    PROCESSED_FOLDER = os.environ.get('PROCESSED_FOLDER', '/home/files/processed')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}