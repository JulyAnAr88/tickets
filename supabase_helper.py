import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import session, request, redirect, url_for, flash
from config import Config
import os

# Inicializar cliente de Supabase con manejo de errores
try:
    from supabase import create_client, Client
    
    # Verificar que las configuraciones existen
    if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
        raise ValueError("SUPABASE_URL y SUPABASE_KEY deben estar configuradas en .env")
    
    supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    print(f"✅ Supabase conectado correctamente a: {Config.SUPABASE_URL}")
    
except ImportError as e:
    print(f"❌ Error importando supabase: {e}")
    print("Ejecuta: pip install supabase==1.0.3")
    supabase = None
    
except Exception as e:
    print(f"❌ Error conectando a Supabase: {e}")
    print(f"URL: {Config.SUPABASE_URL}")
    print(f"KEY: {Config.SUPABASE_KEY[:20]}...")
    supabase = None

def login_required(f):
    """Decorador para proteger rutas que requieren autenticación"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if supabase is None:
            flash('Error de configuración: Supabase no está conectado', 'danger')
            return redirect(url_for('login'))
        
        if 'user' not in session:
            flash('Por favor, inicia sesión para acceder a esta página', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def sign_up_user(email, password, metadata=None):
    """Registrar nuevo usuario en Supabase"""
    if supabase is None:
        return {'success': False, 'message': 'Supabase no está conectado'}
    
    try:
        if metadata is None:
            metadata = {}
        
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": metadata
            }
        })
        
        if response.user:
            return {'success': True, 'user': response.user, 'message': 'Usuario registrado exitosamente'}
        else:
            return {'success': False, 'message': 'Error en el registro'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def sign_in_user(email, password):
    """Iniciar sesión con Supabase"""
    if supabase is None:
        return {'success': False, 'message': 'Supabase no está conectado'}
    
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if response.user:
            # Guardar información del usuario en sesión
            session['user'] = {
                'id': response.user.id,
                'email': response.user.email,
                'avatar_url': response.user.user_metadata.get('avatar_url', ''),
                'full_name': response.user.user_metadata.get('full_name', ''),
                'access_token': response.session.access_token
            }
            return {'success': True, 'user': session['user'], 'message': 'Inicio de sesión exitoso'}
        else:
            return {'success': False, 'message': 'Credenciales inválidas'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def sign_out_user():
    """Cerrar sesión"""
    try:
        if supabase:
            supabase.auth.sign_out()
        session.clear()
        return {'success': True, 'message': 'Sesión cerrada exitosamente'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def get_current_user():
    """Obtener usuario actual de la sesión"""
    return session.get('user', None)

def update_user_metadata(metadata):
    """Actualizar metadata del usuario"""
    if supabase is None:
        return {'success': False, 'message': 'Supabase no está conectado'}
    
    try:
        user = session.get('user')
        if not user:
            return {'success': False, 'message': 'Usuario no autenticado'}
        
        response = supabase.auth.update_user({
            "data": metadata
        })
        
        if response.user:
            session['user']['avatar_url'] = response.user.user_metadata.get('avatar_url', '')
            session['user']['full_name'] = response.user.user_metadata.get('full_name', '')
            return {'success': True, 'message': 'Perfil actualizado'}
        return {'success': False, 'message': 'Error al actualizar'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def upload_avatar(file, user_id):
    """Subir avatar a Supabase Storage"""
    if supabase is None:
        return {'success': False, 'message': 'Supabase no está conectado'}
    
    try:
        # Generar nombre único para el archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"avatars/{user_id}/{timestamp}_{file.filename}"
        
        # Subir archivo a Supabase Storage
        response = supabase.storage.from_('avatars').upload(
            filename,
            file.read(),
            {"content-type": file.content_type}
        )
        
        # Obtener URL pública
        public_url = supabase.storage.from_('avatars').get_public_url(filename)
        
        # Actualizar metadata del usuario con la URL del avatar
        update_user_metadata({'avatar_url': public_url})
        
        return {'success': True, 'url': public_url}
    except Exception as e:
        return {'success': False, 'message': str(e)}