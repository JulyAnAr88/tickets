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
    try:
        if metadata is None:
            metadata = {}
        
        # Asegurar que full_name está en metadata
        if 'full_name' not in metadata:
            metadata['full_name'] = metadata.get('name', email.split('@')[0])
        
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": metadata
            }
        })
        
        if response.user:
            return {
                'success': True, 
                'user': response.user, 
                'message': f'Usuario {metadata.get("full_name")} registrado exitosamente'
            }
        else:
            return {'success': False, 'message': 'Error en el registro'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def sign_in_user(email, password):
    """Iniciar sesión con Supabase"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if response.user:
            # Obtener user_metadata completo
            user_metadata = response.user.user_metadata or {}
            
            # Extraer full_name de diferentes lugares posibles
            full_name = (
                user_metadata.get('full_name') or 
                user_metadata.get('name') or 
                user_metadata.get('fullname') or
                email.split('@')[0]  # Fallback: parte del email
            )
            
            # Guardar toda la información del usuario en sesión
            session.permanent = True
            session['user'] = {
                'id': response.user.id,
                'email': response.user.email,
                'full_name': full_name,
                'avatar_url': user_metadata.get('avatar_url', '')
            }
            
            return {
                'success': True, 
                'user': session['user'], 
                'message': f'Bienvenido {full_name}!'
            }
        else:
            return {'success': False, 'message': 'Credenciales inválidas'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

def get_current_user():
    """Obtener usuario actual de la sesión con datos completos"""
    user = session.get('user', {})
    if not user:
        return None
    
    # Asegurar que full_name existe
    if 'full_name' not in user or not user['full_name']:
        user['full_name'] = user.get('email', '').split('@')[0]
    
    # Asegurar que user_metadata existe (para compatibilidad)
    if 'user_metadata' not in user:
        user['user_metadata'] = {
            'full_name': user['full_name'],
            'email': user.get('email', '')
        }

def get_user_display_name(user=None):
    """Obtiene el nombre para mostrar del usuario"""
    if user is None:
        user = get_current_user()
    
    if not user:
        return 'Usuario'
    
    # Orden de prioridad
    return (
        user.get('full_name') or
        user.get('user_metadata', {}).get('full_name') or
        user.get('user_metadata', {}).get('name') or
        user.get('name') or
        user.get('email', '').split('@')[0] or
        'Usuario'
    )

def sign_out_user():
    """Cerrar sesión"""
    try:
        if supabase:
            supabase.auth.sign_out()
        session.clear()
        return {'success': True, 'message': 'Sesión cerrada exitosamente'}
    except Exception as e:
        return {'success': False, 'message': str(e)}

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

def change_password(current_password, new_password):
    """Cambiar contraseña del usuario autenticado"""
    if supabase is None:
        return {'success': False, 'message': 'Supabase no está conectado'}
    
    try:
        user = session.get('user')
        if not user:
            return {'success': False, 'message': 'Usuario no autenticado'}
        
        # Primero verificar la contraseña actual intentando iniciar sesión
        verify = supabase.auth.sign_in_with_password({
            "email": user['email'],
            "password": current_password
        })
        
        if not verify.user:
            return {'success': False, 'message': 'La contraseña actual no es correcta'}
        
        # Actualizar a la nueva contraseña
        response = supabase.auth.update_user({
            "password": new_password
        })
        
        if response.user:
            return {'success': True, 'message': 'Contraseña actualizada exitosamente'}
        return {'success': False, 'message': 'Error al actualizar la contraseña'}
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