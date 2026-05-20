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
    
    # Configuración de esquemas (cedir para producción, auxiliar para desarrollo local)
    DB_SCHEMA = os.environ.get('DB_SCHEMA', 'cedir')  # Valores: 'cedir' o 'auxiliar'
    
    # Configuración de Supabase
    SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://tu-proyecto.supabase.co')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'tu-supabase-anon-key')
    SUPABASE_JWT_SECRET = os.environ.get('SUPABASE_JWT_SECRET', 'tu-jwt-secret')

    # Gemini API Configuration
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    DATABASE_URL=f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    # Google Cloud Vision API (mucho mejor OCR que Tesseract)
    GOOGLE_CLOUD_VISION_API_KEY = os.environ.get('GOOGLE_CLOUD_VISION_API_KEY', '')
    
    # Prompts Configuration
    PROMPTS_FOLDER = os.environ.get('PROMPTS_FOLDER', 'prompts')

    # Configuración de uploads (para imágenes)
    # UPLOAD_FOLDER = 'static/uploads'
    # PROCESSED_FOLDER = 'static/processed'
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', '/')
    PROCESSED_FOLDER = os.environ.get('PROCESSED_FOLDER', '/')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp','pdf'}
    
    # Superusuario (email con acceso a funciones de admin)
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')
    
    # Service key para operaciones de admin en Supabase (listar/eliminar usuarios)
    SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')
    
    # n8n webhook para OCR
    N8N_OCR_WEBHOOK_URL = os.environ.get('N8N_OCR_WEBHOOK_URL', '')