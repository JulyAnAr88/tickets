import os
import jwt
from datetime import datetime, time, timedelta
from flask import Flask, json, render_template, request, redirect, url_for, flash, jsonify, session, make_response, current_app
from cedir_common import init_cedir
from werkzeug.utils import secure_filename
from config import Config
from models import db, Ticket
from sqlalchemy import text
import supabase_helper
from forms import TicketForm, BuscarForm, ImagenForm
from ticket_processor import FlaskTicketProcessor
from tasks import process_tickets
import requests
from urllib.parse import urlencode
import logging
import json

app = Flask(__name__)
app.config.from_object(Config)

# Configurar sesión permanente (30 días)
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inicialización del procesador de tickets
ticket_processor = None

def init_ticket_processor():
    global ticket_processor
    try:
        ticket_processor = FlaskTicketProcessor(app)
        print("✅ Procesador de tickets inicializado correctamente")
    except Exception as e:
        print(f"⚠️ Error inicializando procesador de tickets: {e}")
        ticket_processor = None

# Configuración de Superset
# SUPERSET_URL = "http://192.168.37.182:8088"

GUEST_TOKEN_JWT_ALGO = "HS256"

def generate_guest_token(dashboard_id, user_info=None):
    """Genera un token guest para embeder dashboards de Superset sin autenticación"""
    if user_info is None:
        user_info = {
            "username": "guest_user",
            "first_name": "Guest",
            "last_name": "User"
        }
    
    exp_time = datetime.utcnow() + timedelta(seconds=3000)
    exp_timestamp = int(exp_time.timestamp())
    
    payload = {
        "user": user_info,
        "resources": [{
            "type": "dashboard",
            "id": str(dashboard_id)
        }],
        "rls_rules": [],
        "exp": exp_timestamp
    }
    
    guest_token_jwt = current_app.config.get("GUEST_TOKEN_JWT_SECRET", "")
    token = jwt.encode(payload, guest_token_jwt, algorithm=GUEST_TOKEN_JWT_ALGO)
    return token

# Inicializar base de datos
init_cedir(app)
db.init_app(app)

# Crear carpetas necesarias
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config.get('PROCESSED_FOLDER', 'static/processed'), exist_ok=True)

# Inicializar procesador de tickets
init_ticket_processor()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.after_request
def add_header(response):
    """Agregar headers para permitir embebidos"""
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    response.headers['Content-Security-Policy'] = "frame-ancestors *"
    return response

@app.context_processor
def inject_now():
    from datetime import datetime
    return {'now': datetime.now()}

@app.before_request
def require_login():
    public_routes = ['login', 'static', 'logout', 'auth_logout', 'cedir_auth.forgot_password', 'cedir_common.static']
    if request.endpoint in public_routes:
        return None
    if 'user' not in session:
        return redirect(url_for('login'))
    return None

# ============ RUTAS DE AUTENTICACIÓN ============

@app.route('/abm/login', methods=['GET', 'POST'])
def login():
    """Página de inicio de sesión"""
    if 'user' in session:
        return redirect(url_for('abm'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        result = supabase_helper.sign_in_user(email, password)
        
        if result['success']:
            flash(result['message'], 'success')
            if result.get('force_password_change'):
                session['force_password_change'] = True
                return redirect(url_for('cambiar_password_obligatorio'))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('abm'))
        else:
            flash(result['message'], 'danger')
    
    return render_template('login.html')

@app.route('/abm/register', methods=['GET', 'POST'])
@supabase_helper.login_required
def register():
    """Página de registro de usuario"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        
        result = supabase_helper.sign_up_user(email, password, {'full_name': full_name})
        
        if result['success']:
            flash('Registro exitoso. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        else:
            flash(result['message'], 'danger')
    
    return render_template('register.html')

@app.route('/abm/logout')
def logout():
    """Cerrar sesión"""
    result = supabase_helper.sign_out_user()
    flash(result['message'], 'success')
    return redirect(url_for('login'))

@app.route('/abm/profile', methods=['GET', 'POST'])
@supabase_helper.login_required
def profile():
    """Perfil de usuario con opción de subir avatar"""
    user = supabase_helper.get_current_user()
    
    if request.method == 'POST':
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                result = supabase_helper.upload_avatar(file, user['id'])
                if result['success']:
                    flash('Avatar actualizado exitosamente', 'success')
                else:
                    flash(f'Error al actualizar avatar: {result["message"]}', 'danger')
        
        # Actualizar nombre completo
        full_name = request.form.get('full_name')
        if full_name and full_name != user.get('full_name'):
            result = supabase_helper.update_user_metadata({'full_name': full_name})
            if result['success']:
                flash('Perfil actualizado exitosamente', 'success')
                user['full_name'] = full_name
            else:
                flash(f'Error al actualizar: {result["message"]}', 'danger')
        
        return redirect(url_for('profile'))
    
    return render_template('profile.html', user=user)

@app.route('/abm/profile/cambiar_password', methods=['POST'])
@supabase_helper.login_required
def cambiar_password():
    """Cambiar contraseña del usuario"""
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    if not current_password or not new_password or not confirm_password:
        flash('Todos los campos son obligatorios', 'warning')
    elif len(new_password) < 6:
        flash('La nueva contraseña debe tener al menos 6 caracteres', 'warning')
    elif new_password != confirm_password:
        flash('Las contraseñas nuevas no coinciden', 'danger')
    else:
        result = supabase_helper.change_password(current_password, new_password)
        if result['success']:
            # Si estaba en cambio obligatorio, quitar flag
            if session.pop('force_password_change', None):
                supabase_helper.update_user_metadata({'force_password_change': False})
            flash(result['message'], 'success')
        else:
            flash(result['message'], 'danger')
    
    return redirect(url_for('profile'))

@app.route('/abm/profile/cambiar_password_obligatorio', methods=['GET', 'POST'])
@supabase_helper.login_required
def cambiar_password_obligatorio():
    """Cambio de contraseña obligatorio (primer inicio de sesión)"""
    if not session.get('force_password_change'):
        return redirect(url_for('profile'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password or not confirm_password:
            flash('Todos los campos son obligatorios', 'warning')
        elif len(new_password) < 6:
            flash('La nueva contraseña debe tener al menos 6 caracteres', 'warning')
        elif new_password != confirm_password:
            flash('Las contraseñas nuevas no coinciden', 'danger')
        else:
            current_password = request.form.get('current_password', '')
            if not current_password:
                flash('Debes ingresar tu contraseña actual', 'warning')
            else:
                result = supabase_helper.change_password(current_password, new_password)
                if result['success']:
                    session.pop('force_password_change', None)
                    supabase_helper.update_user_metadata({'force_password_change': False})
                    flash('Contraseña cambiada exitosamente', 'success')
                    return redirect(url_for('abm'))
                else:
                    flash(result['message'], 'danger')
    
    user = supabase_helper.get_current_user()
    return render_template('cambiar_password_obligatorio.html', user=user)

# ============ RUTAS PROTEGIDAS ============

@app.route('/')
def index():
    """Página de inicio"""
    if 'user' in session:
        return redirect(url_for('abm'))
    return redirect(url_for('login'))

@app.route('/abm', methods=['GET', 'POST'])
@supabase_helper.login_required
def abm():
    """Página unificada con carga de imágenes y listado de tickets"""
    form = ImagenForm()
    user = supabase_helper.get_current_user()
    nombre_usuario = supabase_helper.get_user_display_name(user)
    
    # Inicializar variables
    tickets_pendientes = []
    error_procesamiento = None
    
    # ========== PROCESAR POST (carga de archivo) ==========
    if form.validate_on_submit():
        if not form.imagen.data or not form.imagen.data.filename:
            flash('No se seleccionó ningún archivo', 'warning')
            return redirect(url_for('abm'))
        
        file = form.imagen.data
        filename = file.filename
        extension = filename.split('.')[-1].lower()
        
        if extension not in app.config['ALLOWED_EXTENSIONS']:
            flash(f'Formato "{extension}" no permitido. Use: {", ".join(app.config["ALLOWED_EXTENSIONS"])}', 'danger')
            return redirect(url_for('abm'))
        
        # Guardar archivo temporalmente
        timestamp = int(datetime.now().timestamp())
        safe_filename = f"{timestamp}_{secure_filename(filename)}"
        temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(temp_filepath)
        
        if not ticket_processor:
            flash('Procesador no disponible', 'danger')
            return redirect(url_for('abm'))

        factura_referencia = form.factura_referencia.data or ''
        task = process_tickets.delay(
            file_path=temp_filepath,
            usuario=nombre_usuario,
            schema=app.config.get('DB_SCHEMA', 'cedir'),
            factura_referencia=factura_referencia
        )

        session['processing_task_id'] = task.id
        return redirect(url_for('abm', task_id=task.id))
    
    # ========== PROCESAR GET (cargar página) ==========
    processing_task_id = request.args.get('task_id') or session.pop('processing_task_id', None)
    tickets_pendientes = session.get('tickets_pendientes', [])
    error_procesamiento = session.pop('error_procesamiento', None)
    
    # Obtener parámetros de búsqueda
    termino = request.args.get('termino', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    # Construir query para el listado
    query = Ticket.query
    
    if termino:
        words = termino.strip().split()
        for word in words:
            like_word = f'%{word}%'
            query = query.filter(
                db.or_(
                    Ticket.paciente.ilike(like_word),
                    Ticket.protocolo.ilike(like_word),
                    Ticket.unidad.ilike(like_word),
                    Ticket.usuario.ilike(like_word),
                    Ticket.pasaje.ilike(like_word)
                )
            )
    
    if fecha_desde:
        try:
            fecha_desde_dt = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            query = query.filter(Ticket.fecha_ticket >= fecha_desde_dt)
        except:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            query = query.filter(Ticket.fecha_ticket <= fecha_hasta_dt)
        except:
            pass
    
    tickets = query.order_by(Ticket.create_time.desc()).all()
    
    return render_template('abm.html', 
                         form=form,
                         tickets=tickets,
                         termino=termino,
                         fecha_desde=fecha_desde,
                         fecha_hasta=fecha_hasta,
                         user=user,
                         tickets_pendientes=tickets_pendientes,
                         error_procesamiento=error_procesamiento,
                         processing_task_id=processing_task_id)
    
    
@app.route('/abm/buscar_candidatos', methods=['POST'])
@supabase_helper.login_required
def buscar_candidatos():
    """Busca candidatos similares para un ticket no encontrado"""
    data = request.get_json()
    ticket_id = data.get('ticket_id')
    nombre = data.get('nombre', '')
    dni = data.get('dni', '')
    
    logger.info(f"Buscando candidatos: ticket_id={ticket_id}, nombre='{nombre}', dni='{dni}'")
    
    if not ticket_processor or not ticket_processor.processor:
        return jsonify({'error': 'Procesador no disponible', 'candidates': []}), 500

    try:
        from cedir_common.paciente_service import buscar_candidatos_similares
        candidates = buscar_candidatos_similares(
            ticket_processor.processor.engine,
            nombre_busqueda=nombre,
            dni_busqueda=dni,
            limit=10
        )
        
        logger.info(f"Se encontraron {len(candidates)} candidatos para ticket_id={ticket_id}")
        return jsonify({'candidates': candidates, 'success': True})
    except Exception as e:
        logger.error(f"Error buscando candidatos: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'candidates': [], 'success': False}), 500

@app.route('/abm/seleccionar_paciente', methods=['POST'])
@supabase_helper.login_required
def seleccionar_paciente():
    """Inserta el ticket con el paciente seleccionado manualmente"""
    data = request.get_json()
    ticket_index = data.get('ticket_id')
    paciente_id = data.get('paciente_id')
    ficha_id = data.get('ficha_id')
    nombre = data.get('nombre')
    apellido = data.get('apellido')
    protocolo = data.get('protocolo')
    identificador = data.get('identificador')
    nro_doc = data.get('nro_doc')
    usuario = supabase_helper.get_user_display_name(supabase_helper.get_current_user())
    
    logger.info(f"📋 Selección manual de paciente: ticket_index={ticket_index}, paciente='{nombre} {apellido}', protocolo='{protocolo}', identificador='{identificador}'")
    
    try:
        # Si viene de Geclisa (sin persona_id pero con ficha_id), upsert a cedir primero
        if not paciente_id and ficha_id:
            logger.info(f"🔍 Paciente de Geclisa, creando en cedir (ficha {ficha_id})...")
            try:
                from cedir_common.paciente_service import upsert_paciente_en_cedir
                from sqlalchemy.orm import Session

                protocolo_id = None
                if protocolo and ticket_processor and ticket_processor.processor:
                    protocolo_id = ticket_processor.processor.protocolo_manager._buscar_id_protocolo(protocolo)

                with Session(ticket_processor.processor.engine) as sa_session:
                    result = upsert_paciente_en_cedir(
                        ficha_id=ficha_id,
                        db_session=sa_session,
                        protocolo_id=protocolo_id,
                        identificador=identificador,
                        user_name=usuario,
                        id_herramienta=1,
                    )
                    sa_session.commit()

                paciente_id = result['persona_id']
                logger.info(f"✅ Paciente creado en cedir con persona_id={paciente_id}")
            except Exception as e:
                logger.error(f"Error creando paciente desde Geclisa: {e}", exc_info=True)
                return jsonify({'success': False, 'message': f'Error creando paciente desde Geclisa: {str(e)}'}), 500

        # Obtener los datos extraídos del ticket desde la sesión
        tickets_pendientes = session.get('tickets_pendientes', [])
        logger.debug(f"Tickets pendientes en sesión: {len(tickets_pendientes)}")
        
        # Debug: mostrar todos los índices disponibles
        indices_disponibles = [tp.get('index') for tp in tickets_pendientes]
        logger.debug(f"Índices disponibles: {indices_disponibles}")
        logger.debug(f"Tipo de ticket_index recibido: {type(ticket_index)}, valor: {ticket_index}")
        
        # Normalizar ticket_index a entero para la comparación
        try:
            ticket_index_int = int(ticket_index)
        except (ValueError, TypeError):
            ticket_index_int = ticket_index
            
        # Buscar el ticket pendiente por índice
        ticket_pendiente = None
        for tp in tickets_pendientes:
            tp_index = tp.get('index')
            logger.debug(f"Comparando: tp_index={tp_index} (tipo: {type(tp_index)}) vs ticket_index_int={ticket_index_int} (tipo: {type(ticket_index_int)})")
            if tp_index == ticket_index_int:
                ticket_pendiente = tp
                break
        
        if not ticket_pendiente:
            logger.error(f"❌ Ticket pendiente no encontrado con índice {ticket_index} (normalizado: {ticket_index_int})")
            return jsonify({'success': False, 'message': f'Ticket pendiente no encontrado. Índices disponibles: {indices_disponibles}'}), 404
        
        # Obtener los datos extraídos
        extracted_data = ticket_pendiente.get('extracted_data', {})
        logger.debug(f"Datos extraídos obtenidos: {list(extracted_data.keys())}")
        
        # Debug: mostrar datos completos del ticket para verificar
        logger.info(f"=== DATOS EXTRAÍDOS DEL TICKET ===")
        logger.info(f"  paciente: {extracted_data.get('paciente')}")
        logger.info(f"  viaje: {extracted_data.get('viaje')}")
        logger.info(f"  totales: {extracted_data.get('totales')}")
        logger.info(f"  pasaje: {extracted_data.get('pasaje')}")
        logger.info(f"  fecha_ticket: {extracted_data.get('fecha_ticket')}")
        logger.info(f"  nro_doc: {extracted_data.get('nro_doc')}")
        logger.info(f"  === FIN DATOS EXTRAÍDOS ===")
        
        # Actualizar el extracted_data con los datos del paciente seleccionado
        # Usar el nombre y apellido juntos para el campo "paciente"
        nombre_completo = f"{nombre} {apellido}".strip()
        
        extracted_data['paciente'] = {
            'nombre': nombre_completo,
            'apellido': apellido,
            'persona_id': paciente_id,
            'protocolo': protocolo,
            'nro_doc': nro_doc,
            'encontrado': True,
            'encontrado_por': 'manual'
        }
        
        logger.info(f"✏️ Paciente actualizado en extracted_data: {nombre_completo} (ID: {paciente_id})")
        logger.info(f"✏️ Datos del ticket a insertar - viaje: {extracted_data.get('viaje')}, totales: {extracted_data.get('totales')}")
        
        # Generar SQL e insertar
        if not ticket_processor or not ticket_processor.processor:
            logger.error("❌ Procesador no disponible")
            return jsonify({'success': False, 'message': 'Procesador no disponible'}), 500
        
        sql_query = ticket_processor.processor.generate_insert_sql(extracted_data, usuario)
        logger.info(f"SQL generado: {sql_query}")
        
        insert_result = ticket_processor.processor.insert_ticket(sql_query, '')
        
        if insert_result['success']:
            # Remover el ticket de los pendientes usando comparación consistente
            ticket_index_int = int(ticket_index) if ticket_index else 0
            tickets_pendientes = []
            for tp in session.get('tickets_pendientes', []):
                tp_index = tp.get('index')
                # Convertir a entero para comparación consistente
                tp_index_int = int(tp_index) if tp_index else 0
                if tp_index_int != ticket_index_int:
                    tickets_pendientes.append(tp)
            
            session['tickets_pendientes'] = tickets_pendientes
            session.modified = True
            
            logger.info(f"DEBUG - Tickets después de eliminar: {[tp.get('index') for tp in tickets_pendientes]}")
            
            logger.info(f"✅ Ticket insertado manualmente: {nombre} {apellido} (usuario: {usuario})")
            logger.info(f"📊 Tickets pendientes restantes: {len(tickets_pendientes)}")
            
            return jsonify({
                'success': True, 
                'message': f'Ticket de {nombre} {apellido} insertado correctamente en la base de datos',
                'remaining_pending': len(tickets_pendientes)
            })
        else:
            error_msg = insert_result.get('message', 'Error desconocido')
            logger.error(f"❌ Error insertando ticket: {error_msg}")
            logger.error(f"SQL que falló: {sql_query}")
            
            return jsonify({
                'success': False, 
                'message': f"Error en inserción: {error_msg}"
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Error en seleccionar_paciente: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500

@app.route('/abm/eliminar_pendiente', methods=['POST'])
@supabase_helper.login_required
def eliminar_pendiente():
    """Elimina un ticket pendiente de la sesión sin guardarlo en la base de datos"""
    data = request.get_json()
    ticket_index = data.get('ticket_index')
    
    logger.info(f"🗑️ Eliminando ticket pendiente con índice: {ticket_index}")
    
    try:
        tickets_pendientes = session.get('tickets_pendientes', [])
        
        # Verificar que el ticket existe
        ticket_encontrado = None
        for tp in tickets_pendientes:
            if tp.get('index') == ticket_index:
                ticket_encontrado = tp
                break
        
        if not ticket_encontrado:
            logger.error(f"❌ Ticket pendiente no encontrado con índice {ticket_index}")
            return jsonify({'success': False, 'message': 'Ticket pendiente no encontrado'}), 404
        
        # Remover el ticket de los pendientes
        tickets_pendientes = [tp for tp in tickets_pendientes if tp.get('index') != ticket_index]
        session['tickets_pendientes'] = tickets_pendientes
        session.modified = True
        
        logger.info(f"✅ Ticket pendiente eliminado (índice: {ticket_index})")
        logger.info(f"📊 Tickets pendientes restantes: {len(tickets_pendientes)}")
        
        return jsonify({
            'success': True,
            'message': 'Ticket pendiente eliminado correctamente',
            'remaining_pending': len(tickets_pendientes)
        })
        
    except Exception as e:
        logger.error(f"❌ Error en eliminar_pendiente: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500

@app.route('/abm/limpiar_uploads_huérfanos')
@supabase_helper.login_required
def limpiar_uploads_huérfanos():
    """Limpia archivos en uploads que llevan más de 7 días sin procesar"""
    import time
    upload_folder = app.config['UPLOAD_FOLDER']
    cutoff_time = int(datetime.now().timestamp()) - (7 * 24 * 3600)  # 7 días
    
    eliminados = 0
    for filename in os.listdir(upload_folder):
        filepath = os.path.join(upload_folder, filename)
        if os.path.isfile(filepath):
            if os.path.getmtime(filepath) < cutoff_time:
                os.remove(filepath)
                eliminados += 1
    
    flash(f'Se eliminaron {eliminados} archivos huérfanos', 'info')
    return redirect(url_for('abm'))

@app.route('/abm/recuperar', methods=['GET', 'POST'])
@supabase_helper.login_required
def recuperar_archivos():
    """Página para recuperar archivos huérfanos con caché de n8n"""
    import os, json, glob
    from datetime import datetime as dt
    user = supabase_helper.get_current_user()
    upload_folder = app.config['UPLOAD_FOLDER']
    processed_folder = app.config.get('PROCESSED_FOLDER', 'static/processed')

    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    solo_con_cache = request.args.get('solo_cache', '0') == '1'

    if request.method == 'POST':
        archivos = request.form.getlist('archivos')
        usar_cache = request.form.get('usar_cache', '1') == '1'
        count_ok = 0
        count_err = 0
        todos_pendientes = []
        for filepath in archivos:
            if not os.path.isfile(filepath):
                continue
            try:
                nombre_usuario = supabase_helper.get_user_display_name(user)
                result = ticket_processor.process_uploaded_file(
                    file_path=filepath,
                    usuario=nombre_usuario,
                    move_to_processed=True,
                    validate_protocolo=True,
                    use_cache=usar_cache
                )
                if result and result.get('success', False):
                    count_ok += 1
                else:
                    count_err += 1
                # Acumular tickets pendientes para mostrarlos en ABM
                pendientes = result.get('tickets_pendientes', [])
                if pendientes:
                    todos_pendientes.extend(pendientes)
            except Exception as e:
                logger.error(f"Error reprocesando {filepath}: {e}")
                count_err += 1

        if todos_pendientes:
            session['tickets_pendientes'] = todos_pendientes
            session.modified = True
            flash(f'⚠️ {len(todos_pendientes)} pacientes no identificados requieren selección manual', 'warning')
            return redirect(url_for('abm'))

        flash(f'Reprocesados: {count_ok} ok, {count_err} errores', 'success' if count_err == 0 else 'warning')
        return redirect(url_for('recuperar_archivos'))

    # Listar archivos (incoming + processed)
    archivos_info = []
    carpetas = [
        ('Incoming', upload_folder),
        ('Procesados', processed_folder),
    ]
    for origen, folder in carpetas:
        if not os.path.isdir(folder):
            continue
        for fname in sorted(os.listdir(folder), reverse=True):
            filepath = os.path.join(folder, fname)
            if not os.path.isfile(filepath) or fname.startswith('.') or fname.endswith('.n8n-cache.json'):
                continue
            mtime = dt.fromtimestamp(os.path.getmtime(filepath))
            # Filtro por fecha
            if fecha_desde:
                try:
                    desde = dt.strptime(fecha_desde, '%Y-%m-%d')
                    if mtime < desde:
                        continue
                except:
                    pass
            if fecha_hasta:
                try:
                    hasta = dt.strptime(fecha_hasta, '%Y-%m-%d').replace(hour=23, minute=59)
                    if mtime > hasta:
                        continue
                except:
                    pass

            # Buscar cachés de n8n asociados (en la misma carpeta que el archivo)
            caches = sorted(glob.glob(f"{filepath}.page*.n8n-cache.json"))
            tiene_cache = len(caches) > 0
            if solo_con_cache and not tiene_cache:
                continue

            archivos_info.append({
                'nombre': fname,
                'ruta': filepath,
                'modificado': mtime,
                'tiene_cache': tiene_cache,
                'cant_caches': len(caches),
                'origen': origen,
            })

    return render_template('recuperar.html',
                         archivos=archivos_info,
                         fecha_desde=fecha_desde,
                         fecha_hasta=fecha_hasta,
                         solo_con_cache=solo_con_cache,
                         upload_folder=upload_folder,
                         user=user)

@app.route('/abm/debug/user')
@supabase_helper.login_required
def debug_user():
    user = supabase_helper.get_current_user()
    return jsonify({
        'user': user,
        'user_metadata': user.get('user_metadata', {}),
        'full_name': user.get('full_name'),
        'email': user.get('email')
    })

@app.route('/abm/formulario', methods=['GET', 'POST'])
@supabase_helper.login_required
def formulario():
    form = TicketForm()
    
    if form.validate_on_submit():
        # Procesar imagen
        if form.imagen.data and form.imagen.data.filename:
            file = form.imagen.data
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                import time
                filename = f"{int(int(datetime.now().timestamp()))}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                flash('Imagen cargada exitosamente', 'success')
        
        # Crear nuevo ticket
        ticket = Ticket(
            pasaje=form.pasaje.data,
            paciente=form.paciente.data,
            fecha_viaje=form.fecha_viaje.data,
            fecha_ticket=form.fecha_ticket.data,
            distancia=form.distancia.data,
            unidad=form.unidad.data,
            protocolo=form.protocolo.data,
            subtotal=form.subtotal.data,
            importe_total=form.importe_total.data,
            usuario=form.usuario.data,
            create_time=datetime.utcnow(),
            es_traslado=form.es_traslado.data,
            factura_referencia=form.factura_referencia.data
        )
        
        try:
            db.session.add(ticket)
            db.session.commit()
            flash('Ticket guardado exitosamente', 'success')
            return redirect(url_for('abm'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar: {str(e)}', 'danger')
    
    return render_template('formulario.html', form=form)

@app.route('/abm/eliminar_multiples', methods=['POST'])
@supabase_helper.login_required
def eliminar_multiples():
    """Eliminar múltiples tickets seleccionados (con cascade manual por ticket_procesado)"""
    ticket_ids = request.form.getlist('ticket_ids')
    
    if not ticket_ids:
        flash('No se seleccionaron tickets para eliminar', 'warning')
        return redirect(url_for('abm'))
    
    success_count = 0
    error_count = 0
    
    ids = [int(x) for x in ticket_ids]
    
    try:
        schema = get_db_schema()
        db.session.execute(
            text(f"DELETE FROM {schema}.ticket_procesado WHERE id_ticket = ANY(:ids)"),
            {'ids': ids}
        )
        db.session.execute(
            text(f"DELETE FROM {schema}.ticket WHERE id = ANY(:ids)"),
            {'ids': ids}
        )
        db.session.commit()
        success_count = len(ids)
        flash(f'Se eliminaron {success_count} ticket(s) correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error eliminando tickets: {e}")
        flash(f'Error al eliminar los tickets: {str(e)}', 'danger')
    
    return redirect(url_for('abm'))

@app.route('/abm/listado')
@supabase_helper.login_required
def listado():
    """Listado completo de tickets"""
    user = supabase_helper.get_current_user()
    termino = request.args.get('termino', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    query = Ticket.query
    
    if termino:
        words = termino.strip().split()
        for word in words:
            like_word = f'%{word}%'
            query = query.filter(
                db.or_(
                    Ticket.paciente.ilike(like_word),
                    Ticket.protocolo.ilike(like_word),
                    Ticket.pasaje.ilike(like_word),
                    Ticket.usuario.ilike(like_word)
                )
            )
    
    if fecha_desde:
        try:
            fecha_desde_dt = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            query = query.filter(Ticket.fecha_ticket >= fecha_desde_dt)
        except:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            query = query.filter(Ticket.fecha_ticket <= fecha_hasta_dt)
        except:
            pass
    
    tickets = query.order_by(Ticket.create_time.desc()).all()
    
    return render_template('listado.html', tickets=tickets, 
                         termino=termino, fecha_desde=fecha_desde, 
                         fecha_hasta=fecha_hasta, user=user)

@app.route('/abm/editar/<int:id>', methods=['GET', 'POST'])
@supabase_helper.login_required
def editar(id):
    """Editar ticket - solo accesible con login"""
    ticket = Ticket.query.get_or_404(id)
    form = TicketForm(obj=ticket)
    user = supabase_helper.get_current_user()
    protocolos_sugeridos = []
    if ticket_processor:
        protocolos_sugeridos = ticket_processor.get_all_protocolos()
    
    if form.validate_on_submit():
        ticket.pasaje = form.pasaje.data
        ticket.paciente = form.paciente.data
        ticket.fecha_viaje = form.fecha_viaje.data
        ticket.fecha_ticket = form.fecha_ticket.data
        ticket.distancia = form.distancia.data
        ticket.unidad = form.unidad.data
        ticket.protocolo = form.protocolo.data
        ticket.tipo_visita = form.tipo_visita.data
        ticket.requiere_cuidador = form.requiere_cuidador.data
        ticket.es_contingencia = form.es_contingencia.data
        ticket.horas_duracion_visita = form.horas_duracion_visita.data
        ticket.cantidad_comidas = form.cantidad_comidas.data or 1
        ticket.cantidad_noches = form.cantidad_noches.data or 0
        ticket.preseleccion_no_completo = form.preseleccion_no_completo.data
        ticket.es_traslado = form.es_traslado.data
        ticket.factura_referencia = form.factura_referencia.data
        ticket.subtotal = form.subtotal.data
        ticket.importe_total = form.importe_total.data
        nombre_usuario = user.get('full_name') or \
                        user.get('user_metadata', {}).get('full_name') or \
                        user.get('user_metadata', {}).get('name') or \
                        user.get('email', '').split('@')[0] or \
                        'Usuario'
        ticket.usuario = nombre_usuario
        
        # Procesar nueva imagen si se subió
        if form.imagen.data and form.imagen.data.filename:
            file = form.imagen.data
            if file and allowed_file(file.filename):
                if ticket.imagen_path:
                    old_file = os.path.join(app.config['UPLOAD_FOLDER'], 
                                           os.path.basename(ticket.imagen_path))
                    if os.path.exists(old_file):
                        os.remove(old_file)
                
                filename = secure_filename(file.filename)
                import time
                filename = f"{int(int(datetime.now().timestamp()))}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                ticket.imagen_path = f"uploads/{filename}"
                flash('Imagen actualizada', 'success')
        
        try:
            db.session.commit()
            flash('Ticket actualizado exitosamente', 'success')
            return redirect(url_for('abm'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')
    
    return render_template('editar.html', form=form, ticket=ticket, 
                         user=user, protocolos_sugeridos=protocolos_sugeridos)

@app.route('/abm/eliminar/<int:id>')
@supabase_helper.login_required
def eliminar(id):
    """Eliminar ticket con sus reintegros asociados"""
    ticket = Ticket.query.get_or_404(id)
    
    try:
        esquema_actual = current_app.config.get('DB_SCHEMA', 'cedir')
        
        # Eliminar reintegros asociados manualmente
        db.session.execute(
            text(f"DELETE FROM {esquema_actual}.ticket_procesado WHERE id_ticket = :ticket_id"),
            {'ticket_id': ticket.id}
        )
        
        db.session.delete(ticket)
        db.session.commit()
        flash('Ticket y reintegros asociados eliminados exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    
    return redirect(url_for('abm'))

@app.route('/abm/eliminar_con_reintegros/<int:id>', methods=['POST'])
@supabase_helper.login_required
def eliminar_con_reintegros(id):
    """Eliminar ticket Y sus reintegros asociados (borrado en cascada)"""
    logger.info(f"🗑️ Eliminando ticket {id} con reintegros...")
    
    ticket = Ticket.query.get_or_404(id)
    
    try:
        # Obtener el esquema actual
        esquema_actual = current_app.config.get('DB_SCHEMA', 'cedir')
        
        # Verificar si hay reintegros asociados ANTES de eliminar
        reintegros_count = 0
        try:
            reintegros_count = db.session.execute(
                text(f"SELECT COUNT(*) FROM {esquema_actual}.ticket_procesado WHERE id_ticket = :ticket_id"),
                {'ticket_id': ticket.id}
            ).scalar() or 0
            logger.info(f"📊 Reinentos asociados encontrados: {reintegros_count}")
        except Exception as e:
            logger.warning(f"⚠️ Error consultando reintegros: {e}")
        
        # Primero eliminar los reintegros manualmente (por si el trigger no funciona)
        if reintegros_count > 0:
            try:
                result = db.session.execute(
                    text(f"DELETE FROM {esquema_actual}.ticket_procesado WHERE id_ticket = :ticket_id"),
                    {'ticket_id': ticket.id}
                )
                logger.info(f"✅ Eliminados {result.rowcount} reintegros manualmente")
            except Exception as e:
                logger.warning(f"⚠️ Error eliminando reintegros manualmente: {e}")
        
        # Eliminar ticket
        db.session.delete(ticket)
        db.session.commit()
        logger.info(f"✅ Ticket {id} eliminado correctamente")
        
        if reintegros_count > 0:
            flash(f'Ticket y {reintegros_count} reintegro(s) relacionado(s) eliminados', 'success')
        else:
            flash('Ticket eliminado exitosamente', 'success')
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ Error al eliminar ticket {id}: {e}")
        flash(f'Error al eliminar: {str(e)}', 'danger')
    
    return redirect(url_for('abm'))

def get_db_schema():
    """Obtiene el esquema de base de datos actual desde la configuración"""
    return current_app.config.get('DB_SCHEMA', 'cedir')

@app.route('/abm/procesar/<int:id>', methods=['POST'])
@supabase_helper.login_required
def procesar_ticket(id):
    """Procesar un ticket existente (reprocesar imagen con IA)"""
    ticket = Ticket.query.get_or_404(id)
    
    if not ticket.imagen_path:
        flash('El ticket no tiene imagen asociada', 'warning')
        return redirect(url_for('abm'))
    
    if not ticket_processor:
        flash('Procesador de tickets no disponible', 'danger')
        return redirect(url_for('abm'))
    
    # Ruta completa de la imagen
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(ticket.imagen_path))
    
    if not os.path.exists(image_path):
        flash('El archivo de imagen no existe en el servidor', 'danger')
        return redirect(url_for('abm'))
    
    try:
        # Procesar la imagen
        result = ticket_processor.process_uploaded_file(image_path, move_to_processed=False)
        
        if result['success']:
            # Actualizar el ticket con los datos extraídos
            if 'steps' in result and 'extraction' in result['steps']:
                extracted = result['steps']['extraction']
                
                # Actualizar campos del ticket con los datos extraídos
                if extracted.get('paciente') and len(extracted['paciente']) > 0:
                    ticket.paciente = extracted['paciente'][0].get('nombre', ticket.paciente)
                    ticket.protocolo = extracted['paciente'][0].get('protocolo', ticket.protocolo)
                
                if extracted.get('viaje') and len(extracted['viaje']) > 0:
                    viaje = extracted['viaje'][0]
                    if viaje.get('fecha_viaje'):
                        try:
                            ticket.fecha_viaje = datetime.strptime(viaje['fecha_viaje'], '%d/%m/%Y').date()
                        except:
                            pass
                    ticket.distancia = viaje.get('distancia', ticket.distancia)
                    ticket.unidad = viaje.get('unidad', ticket.unidad)
                    if ticket.distancia or ticket.unidad:
                        ticket.es_traslado = True
                
                if extracted.get('es_traslado'):
                    ticket.es_traslado = extracted['es_traslado']
                
                if extracted.get('fecha_ticket'):
                    try:
                        ticket.fecha_ticket = datetime.strptime(extracted['fecha_ticket'], '%d/%m/%Y').date()
                    except:
                        pass
                
                if extracted.get('totales'):
                    ticket.subtotal = extracted['totales'].get('subtotal', ticket.subtotal)
                    ticket.importe_total = extracted['totales'].get('importe_total', ticket.importe_total)
                
                                
                db.session.commit()
                flash('Ticket procesado y actualizado correctamente con datos de IA', 'success')
            else:
                flash('No se pudieron extraer datos de la imagen', 'warning')
        else:
            flash(f'Error al procesar: {result["message"]}', 'danger')
            
    except Exception as e:
        flash(f'Error en procesamiento: {str(e)}', 'danger')
    
    return redirect(url_for('abm'))

@app.route('/abm/buscar')
def buscar():
    termino = request.args.get('termino', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    query = Ticket.query
    
    if termino:
        words = termino.strip().split()
        for word in words:
            like_word = f'%{word}%'
            query = query.filter(
                db.or_(
                    Ticket.paciente.ilike(like_word),
                    Ticket.protocolo.ilike(like_word),
                    Ticket.unidad.ilike(like_word),
                    Ticket.usuario.ilike(like_word)
                )
            )
    
    if fecha_desde:
        try:
            fecha_desde_dt = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            query = query.filter(Ticket.fecha_ticket >= fecha_desde_dt)
        except:
            pass
    
    if fecha_hasta:
        try:
            fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            query = query.filter(Ticket.fecha_ticket <= fecha_hasta_dt)
        except:
            pass
    
    tickets = query.order_by(Ticket.create_time.desc()).all()
    return render_template('listado.html', tickets=tickets, termino=termino, 
                         fecha_desde=fecha_desde, fecha_hasta=fecha_hasta)

@app.route('/abm/api/tickets')
@supabase_helper.login_required
def api_tickets():
    tickets = Ticket.query.all()
    return jsonify([ticket.to_dict() for ticket in tickets])

@app.route('/abm/api/pacientes/suggestions')
@supabase_helper.login_required
def api_pacientes_suggestions():
    """API para sugerencias de pacientes (autocompletado)"""
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    
    if ticket_processor and ticket_processor.processor:
        suggestions = ticket_processor.processor.protocolo_manager.get_paciente_suggestions(query)
        return jsonify(suggestions)
    
    return jsonify([])

@app.route('/abm/api/protocolos/suggestions')
@supabase_helper.login_required
def api_protocolos_suggestions():
    """API para sugerencias de protocolos (autocompletado)"""
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    
    if ticket_processor and ticket_processor.processor:
        protocolos = ticket_processor.processor.protocolo_manager.get_all_protocolos()
        # Filtrar por coincidencia
        matches = [p for p in protocolos if query.lower() in p.lower()]
        return jsonify(matches[:10])
    
    return jsonify([])

@app.route('/abm/api/protocolos/lista')
@supabase_helper.login_required
def api_protocolos_lista():
    """API para obtener todos los protocolos (con id)"""
    if ticket_processor and ticket_processor.processor:
        protocolos = ticket_processor.processor.protocolo_manager.get_all_protocolos_con_id()
        return jsonify(protocolos)
    return jsonify([])

# =====================================================
# CRUD Criterios de Reintegro
# =====================================================

def get_schema():
    return current_app.config.get('DB_SCHEMA', 'cedir')

@app.route('/abm/reintegros')
@supabase_helper.login_required
def criterios_reintegro():
    schema = get_schema()
    engine = ticket_processor.processor.engine if ticket_processor and ticket_processor.processor else None
    protocolos = []
    conceptos = []
    condiciones = []
    montos = []
    requisitos = []
    if engine:
        with engine.connect() as conn:
            protocolos = [dict(r) for r in conn.execute(text(
                f"SELECT id, identificador_protocolo FROM {schema}.protocolo ORDER BY identificador_protocolo"
            ))]
            conceptos = [dict(r) for r in conn.execute(text(
                f"SELECT id, descripcion, categoria FROM {schema}.concepto_reintegro ORDER BY categoria, descripcion"
            ))]
            condiciones = [dict(r) for r in conn.execute(text(
                f"SELECT c.id, c.descripcion, tc.codigo as tipo_codigo, c.parametro_evaluacion "
                f"FROM {schema}.condicion_reintegro c "
                f"JOIN {schema}.tipo_condicion tc ON c.id_tipo_condicion = tc.id "
                f"ORDER BY tc.codigo, c.descripcion"
            ))]
            montos = [dict(r) for r in conn.execute(text(
                f"SELECT id, tipo, valor_numerico, unidad, texto_extra FROM {schema}.monto_reintegro ORDER BY tipo"
            ))]
            requisitos = [dict(r) for r in conn.execute(text(
                f"SELECT id, descripcion FROM {schema}.requisito_reintegro ORDER BY descripcion"
            ))]
    return render_template('criterios_reintegro.html',
                         protocolos=protocolos, conceptos=conceptos,
                         condiciones=condiciones, montos=montos,
                         requisitos=requisitos, schema=schema,
                         user=supabase_helper.get_current_user())

@app.route('/abm/reintegros/api/listar/<int:protocolo_id>')
@supabase_helper.login_required
def api_listar_reintegros(protocolo_id):
    schema = get_schema()
    engine = ticket_processor.processor.engine if ticket_processor and ticket_processor.processor else None
    if not engine:
        return jsonify({'error': 'Motor no disponible'})
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT
                    pr.id_protocolo, pr.id_reintegro,
                    r.id_concepto, c.descripcion as concepto, c.categoria,
                    r.id_condicion, cond.descripcion as condicion,
                    tc.codigo as tipo_codigo, cond.parametro_evaluacion,
                    r.id_monto, m.tipo as monto_tipo, m.valor_numerico as monto_valor,
                    m.unidad as monto_unidad,
                    r.id_requisito, req.descripcion as requisito
                FROM {schema}.protocolo_reintegro pr
                JOIN {schema}.reintegro r ON pr.id_reintegro = r.id
                JOIN {schema}.concepto_reintegro c ON r.id_concepto = c.id
                JOIN {schema}.condicion_reintegro cond ON r.id_condicion = cond.id
                JOIN {schema}.tipo_condicion tc ON cond.id_tipo_condicion = tc.id
                JOIN {schema}.monto_reintegro m ON r.id_monto = m.id
                LEFT JOIN {schema}.requisito_reintegro req ON r.id_requisito = req.id
                WHERE pr.id_protocolo = :pid
                ORDER BY c.categoria, r.id
            """), {'pid': protocolo_id})
            reglas = [dict(r._mapping) for r in rows]
            return jsonify({'reglas': reglas})
    except Exception as e:
        logger.error(f"Error listando reintegros: {e}", exc_info=True)
        return jsonify({'error': str(e)})

@app.route('/abm/reintegros/api/agregar', methods=['POST'])
@supabase_helper.login_required
def api_agregar_reintegro():
    schema = get_schema()
    data = request.get_json()
    id_protocolo = data.get('id_protocolo')
    id_concepto = data.get('id_concepto')
    id_condicion = data.get('id_condicion')
    id_monto = data.get('id_monto')
    id_requisito = data.get('id_requisito')
    if not all([id_protocolo, id_concepto, id_condicion, id_monto]):
        return jsonify({'error': 'Faltan campos obligatorios'})
    engine = ticket_processor.processor.engine if ticket_processor and ticket_processor.processor else None
    if not engine:
        return jsonify({'error': 'Motor no disponible'})
    try:
        with engine.connect() as conn:
            with conn.begin():
                result = conn.execute(text(f"""
                    INSERT INTO {schema}.reintegro (id_concepto, id_condicion, id_monto, id_requisito)
                    VALUES (:ic, :icond, :im, :ireq)
                    RETURNING id
                """), {'ic': id_concepto, 'icond': id_condicion, 'im': id_monto, 'ireq': id_requisito or None})
                new_id = result.fetchone()[0]
                conn.execute(text(f"""
                    INSERT INTO {schema}.protocolo_reintegro (id_protocolo, id_reintegro)
                    VALUES (:ip, :ir)
                    ON CONFLICT DO NOTHING
                """), {'ip': id_protocolo, 'ir': new_id})
            return jsonify({'success': True, 'id_reintegro': new_id})
    except Exception as e:
        logger.error(f"Error agregando reintegro: {e}", exc_info=True)
        return jsonify({'error': str(e)})

@app.route('/abm/reintegros/api/editar/<int:id_reintegro>', methods=['POST'])
@supabase_helper.login_required
def api_editar_reintegro(id_reintegro):
    schema = get_schema()
    data = request.get_json()
    id_concepto = data.get('id_concepto')
    id_condicion = data.get('id_condicion')
    id_monto = data.get('id_monto')
    id_requisito = data.get('id_requisito')
    if not all([id_concepto, id_condicion, id_monto]):
        return jsonify({'error': 'Faltan campos obligatorios'})
    engine = ticket_processor.processor.engine if ticket_processor and ticket_processor.processor else None
    if not engine:
        return jsonify({'error': 'Motor no disponible'})
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text(f"""
                    UPDATE {schema}.reintegro
                    SET id_concepto = :ic, id_condicion = :icond, id_monto = :im, id_requisito = :ireq
                    WHERE id = :idr
                """), {'ic': id_concepto, 'icond': id_condicion, 'im': id_monto, 'ireq': id_requisito or None, 'idr': id_reintegro})
            return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error editando reintegro: {e}", exc_info=True)
        return jsonify({'error': str(e)})

@app.route('/abm/reintegros/api/eliminar', methods=['POST'])
@supabase_helper.login_required
def api_eliminar_reintegro():
    schema = get_schema()
    data = request.get_json()
    id_protocolo = data.get('id_protocolo')
    id_reintegro = data.get('id_reintegro')
    if not all([id_protocolo, id_reintegro]):
        return jsonify({'error': 'Faltan id_protocolo y id_reintegro'})
    engine = ticket_processor.processor.engine if ticket_processor and ticket_processor.processor else None
    if not engine:
        return jsonify({'error': 'Motor no disponible'})
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text(f"DELETE FROM {schema}.protocolo_reintegro WHERE id_protocolo = :ip AND id_reintegro = :ir"),
                           {'ip': id_protocolo, 'ir': id_reintegro})
                conn.execute(text(f"DELETE FROM {schema}.reintegro WHERE id = :ir"),
                           {'ir': id_reintegro})
            return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error eliminando reintegro: {e}", exc_info=True)
        return jsonify({'error': str(e)})

@app.route('/abm/superset')
@supabase_helper.login_required
def superset():
    """Vista para embeber dashboard de Superset"""
    guest_token = generate_guest_token(1)
    superset_url = current_app.config.get("SUPERSET_URL", "http://localhost:8088")
    dashboard_slug = current_app.config.get("DASHBOARD_SLUG", "ticket")  # Cambiar según el dashboard que quieras mostrar
    dashboard_url = f"{superset_url}/superset/dashboard/{dashboard_slug}/?standalone=true&expand_filters=0&guest_token={guest_token}"
    return render_template("superset_dashboard.html", 
                         dashboard_url=dashboard_url,
                         guest_token=guest_token,
                         dashboard_id=1,
                         superset_url=superset_url,
                         dashboard_slug=dashboard_slug,
                         user=supabase_helper.get_current_user())

# =====================================================
# Rutas de Autenticación con Google OAuth
# =====================================================

@app.route('/abm/auth/google')
def auth_google():
    """Redirigir a Google para autenticación OAuth"""
    try:
        # Construir la URL de autorización de Google
        from urllib.parse import urlencode
        
        # Obtener la URL de callback
        callback_url = url_for('auth_google_callback', _external=True)
        
        # Parámetros para Google OAuth
        params = {
            'client_id': current_app.config.get('SUPABASE_KEY', ''),  # Usar como referencia
            'redirect_uri': callback_url,
            'response_type': 'code',
            'scope': 'email profile',
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        # En Supabase, el flujo real se maneja a través de su URL de autenticación
        # Redirigir al login de Supabase con provider=google
        supabase_url = current_app.config.get('SUPABASE_URL', '')
        auth_url = f"{supabase_url}/auth/v1/authorize?provider=google&redirect_to={callback_url}"
        
        logger.info(f"🔐 Redirigiendo a Google Auth: {auth_url}")
        
        return redirect(auth_url)
        
    except Exception as e:
        logger.error(f"Error en autenticación Google: {e}")
        flash(f'Error al iniciar sesión con Google: {str(e)}', 'danger')
        return redirect(url_for('login'))

@app.route('/abm/auth/google/callback')
def auth_google_callback():
    """Callback después de autenticación con Google"""
    try:
        # El token viene en la URL como código que debe intercambiarse
        # Por ahora, simplemente verificamos si hay un error o redirigimos al login
        error = request.args.get('error')
        
        if error:
            flash(f'Error de autenticación: {error}', 'danger')
            return redirect(url_for('login'))
        
        # Si hay código, intentar trocar por sesión
        code = request.args.get('code')
        if code:
            # Intercambiar código por sesión (esto requiere configuración en Supabase)
            flash('Autenticación exitosa. Por favor, iniciá sesión.', 'success')
        
        return redirect(url_for('abm'))
        
    except Exception as e:
        logger.error(f"Error en callback de Google: {e}")
        flash(f'Error en autenticación: {str(e)}', 'danger')
        return redirect(url_for('login'))

@app.route('/abm/auth/logout')
@supabase_helper.login_required
def auth_logout():
    """Cerrar sesión"""
    try:
        # Limpiar session
        session.clear()
        flash('Sesión cerrada correctamente', 'success')
    except Exception as e:
        logger.error(f"Error al cerrar sesión: {e}")
    
    return redirect(url_for('login'))

@app.route('/abm/admin/crear_usuario', methods=['GET', 'POST'])
@supabase_helper.login_required
def admin_crear_usuario():
    """Crear usuarios operativos - solo para superusuario"""
    from flask import request
    from config import Config
    
    current_user = supabase_helper.get_current_user()
    admin_email = app.config.get('ADMIN_EMAIL', 'admin@cedir.com')
    
    if current_user.get('email') != admin_email:
        flash('No tienes permisos de administrador', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        
        if not email or not password or not full_name:
            flash('Todos los campos son obligatorios', 'warning')
        elif len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'warning')
        else:
            result = supabase_helper.sign_up_user(
                email=email,
                password=password,
                metadata={'full_name': full_name, 'force_password_change': True}
            )
            
            if result.get('success'):
                flash(f'Usuario {full_name} ({email}) creado exitosamente', 'success')
            else:
                flash(f'Error al crear usuario: {result.get("message")}', 'danger')
        
        return redirect(url_for('admin_crear_usuario'))
    
    return render_template('admin_crear_usuario.html')

@app.route('/abm/task_status/<task_id>')
def task_status(task_id):
    task = process_tickets.AsyncResult(task_id)
    if task.state == 'PENDING':
        return jsonify({'state': 'PENDING', 'status': 'Esperando para procesar...'})
    elif task.state == 'STARTED':
        return jsonify({'state': 'STARTED', 'status': 'Procesando...'})
    elif task.state == 'RETRY':
        return jsonify({'state': 'RETRY', 'status': 'Reintentando...'})
    elif task.state == 'SUCCESS':
        return jsonify({'state': 'SUCCESS', 'result': task.result})
    elif task.state == 'FAILURE':
        error_msg = str(task.info)
        if hasattr(task.info, 'traceback'):
            error_msg = task.info.traceback or error_msg
        return jsonify({'state': 'FAILURE', 'error': error_msg})
    else:
        return jsonify({'state': task.state, 'status': str(task.info)[:200]})

@app.route('/abm/finalize_task/<task_id>', methods=['POST'])
def finalize_task(task_id):
    task = process_tickets.AsyncResult(task_id)
    if task.state != 'SUCCESS':
        return jsonify({'success': False, 'error': 'Tarea no completada'}), 400

    result = task.result
    if not result:
        flash('Error: el procesamiento no retornó resultados', 'danger')
        return jsonify({'success': True})

    if result.get('tickets_automaticos'):
        flash(f'✅ {len(result["tickets_automaticos"])} tickets insertados automáticamente', 'success')

    pendientes = result.get('tickets_pendientes', [])
    if pendientes:
        session['tickets_pendientes'] = pendientes
        flash(f'⚠️ Se encontraron {len(pendientes)} pacientes no identificados.', 'warning')

    if result.get('tickets_con_error'):
        flash(f'❌ {len(result["tickets_con_error"])} tickets con error de procesamiento', 'danger')

    if result.get('archivo_movido'):
        flash(f'📁 Archivo archivado en processed', 'info')
    elif result.get('tickets_insertados', 0) == 0 and not pendientes:
        flash(f'❌ No se insertaron tickets. El archivo queda pendiente para revisión.', 'danger')

    if result.get('errores'):
        session['error_procesamiento'] = {
            'mensaje': result.get('message', 'Error en procesamiento'),
            'errores': result.get('errores'),
            'tickets_insertados': result.get('tickets_insertados', 0)
        }

    return jsonify({'success': True})

@app.route('/abm/nuevo_ticket', methods=['GET', 'POST'])
@supabase_helper.login_required
def nuevo_ticket():
    """Crea un ticket manualmente sin escaneo"""
    from datetime import datetime
    user = supabase_helper.get_current_user()
    usuario = supabase_helper.get_user_display_name(user)

    if request.method == 'POST':
        try:
            data = {
                'paciente': {
                    'nombre': request.form.get('paciente', '').strip(),
                    'persona_id': request.form.get('id_paciente') or None,
                    'protocolo': request.form.get('protocolo', '').strip(),
                },
                'viaje': {
                    'fecha_viaje': request.form.get('fecha_viaje', '').strip(),
                    'distancia': request.form.get('distancia') or None,
                    'unidad': request.form.get('unidad', 'km').strip(),
                },
                'totales': {
                    'importe_total': request.form.get('importe_total', '').strip(),
                },
                'fecha_ticket': request.form.get('fecha_ticket', '').strip(),
                'pasaje': request.form.get('pasaje', '').strip(),
                'es_traslado': request.form.get('es_traslado') == '1',
                'factura_referencia': request.form.get('factura_referencia', '').strip(),
            }

            if not data['paciente']['nombre']:
                flash('El nombre del paciente es obligatorio', 'danger')
                return render_template('nuevo_ticket.html', now=datetime.now())

            if not ticket_processor or not ticket_processor.processor:
                flash('Procesador no disponible', 'danger')
                return render_template('nuevo_ticket.html', now=datetime.now())

            sql = ticket_processor.processor.generate_insert_sql(data, usuario)
            result = ticket_processor.processor.insert_ticket(sql, '')

            if result['success']:
                flash(f'✅ Ticket creado correctamente para {data["paciente"]["nombre"]}', 'success')
                return redirect(url_for('abm'))
            else:
                flash(f'Error al insertar: {result.get("message", "Error desconocido")}', 'danger')
        except Exception as e:
            logger.error(f"Error creando ticket manual: {e}", exc_info=True)
            flash(f'Error: {str(e)}', 'danger')

    protocolos = []
    if ticket_processor and ticket_processor.processor:
        try:
            protocolos = ticket_processor.processor.protocolo_manager.get_all_protocolos_con_id()
        except Exception as e:
            logger.error(f"Error cargando protocolos: {e}")

    return render_template('nuevo_ticket.html', now=datetime.now(), protocolos=protocolos)

@app.route('/abm/nuevo_ticket/buscar_paciente', methods=['POST'])
@supabase_helper.login_required
def nuevo_ticket_buscar_paciente():
    """Busca pacientes para el formulario nuevo ticket: PG primero, Geclisa fallback"""
    data = request.get_json()
    nombre = (data.get('nombre') or '').strip()
    dni = (data.get('dni') or '').strip()

    if not nombre and not dni:
        return jsonify({'candidates': [], 'success': True})

    candidates = []
    try:
        from cedir_common.paciente_service import buscar_candidatos_similares, limpiar_dni
        engine = ticket_processor.processor.engine

        candidates = buscar_candidatos_similares(engine, nombre_busqueda=nombre, dni_busqueda=dni, limit=8)

        # Get identificador for PostgreSQL candidates
        if candidates:
            with engine.connect() as conn:
                for c in candidates:
                    if c.get('persona_id'):
                        row = conn.execute(text(
                            "SELECT identificador FROM cedir.paciente_protocolo "
                            "WHERE id_paciente = (SELECT id FROM cedir.paciente WHERE id_persona = :pid LIMIT 1) "
                            "LIMIT 1"
                        ), {'pid': c['persona_id']}).fetchone()
                        c['identificador'] = row[0] if row else ''
                    else:
                        c['identificador'] = ''

        return jsonify({'candidates': candidates, 'success': True})
    except Exception as e:
        logger.error(f"Error buscando paciente: {e}", exc_info=True)
        return jsonify({'candidates': candidates, 'success': False, 'error': str(e)}), 500


def init_db():
    """Inicializar esquema de base de datos (search_path + tablas)"""
    with app.app_context():
        esquema = app.config.get('DB_SCHEMA', 'cedir')
        print(f"🔧 Usando esquema de base de datos: {esquema}")
        db.session.execute(text(f"SET search_path TO {esquema}"))
        db.create_all()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5001)
