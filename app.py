import os
import jwt
from datetime import datetime, time, timedelta
from flask import Flask, json, render_template, request, redirect, url_for, flash, jsonify, session, make_response, current_app
from werkzeug.utils import secure_filename
from config import Config
from models import db, Ticket
from sqlalchemy import text
import supabase_helper
from forms import TicketForm, BuscarForm, ImagenForm
from ticket_processor import FlaskTicketProcessor
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

# Inicialización lazy del procesador de tickets (para no cargar numpy/PIL/Gemini al arranque)
_ticket_processor = None

def get_ticket_processor():
    global _ticket_processor
    if _ticket_processor is None:
        try:
            _ticket_processor = FlaskTicketProcessor(app)
            print("✅ Procesador de tickets inicializado correctamente")
        except Exception as e:
            print(f"⚠️ Error inicializando procesador de tickets: {e}")
            _ticket_processor = None
    return _ticket_processor

# Configuración de Superset
SUPERSET_URL = "http://192.168.37.182:8088"
GUEST_TOKEN_JWT_SECRET = "3c7c2f380ee1e034889c7bb263d2f6850cde8a8a4151c0c4f8b2ef1f30e897e2"
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
    
    token = jwt.encode(payload, GUEST_TOKEN_JWT_SECRET, algorithm=GUEST_TOKEN_JWT_ALGO)
    return token

# Inicializar base de datos
db.init_app(app)

# Crear carpetas necesarias
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config.get('PROCESSED_FOLDER', 'static/processed'), exist_ok=True)

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
    public_routes = ['login', 'static', 'logout', 'auth_logout']
    if request.endpoint in public_routes:
        return None
    if 'user' not in session:
        return redirect(url_for('login'))
    return None

# ============ RUTAS DE AUTENTICACIÓN ============

@app.route('/login', methods=['GET', 'POST'])
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

@app.route('/register', methods=['GET', 'POST'])
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

@app.route('/logout')
def logout():
    """Cerrar sesión"""
    result = supabase_helper.sign_out_user()
    flash(result['message'], 'success')
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
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

@app.route('/profile/cambiar_password', methods=['POST'])
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

@app.route('/profile/cambiar_password_obligatorio', methods=['GET', 'POST'])
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
        
        # Procesar archivo
        process_result = ticket_processor.process_uploaded_file(
            file_path=temp_filepath,
            usuario=nombre_usuario,
            move_to_processed=True
        )
        
        if process_result is None:
            flash('Error: El procesador retornó un resultado vacío', 'danger')
            return redirect(url_for('abm'))
        
        # Mostrar mensajes según resultados
        if process_result.get('tickets_automaticos'):
            flash(f'✅ {len(process_result["tickets_automaticos"])} tickets insertados automáticamente', 'success')
        
        pendientes = process_result.get('tickets_pendientes', [])
        if pendientes:
            # Guardar en session para la siguiente request
            session['tickets_pendientes'] = pendientes
            flash(f'⚠️ Se encontraron {len(pendientes)} pacientes no identificados. Por favor selecciona la opción correcta.', 'warning')
        
        if process_result.get('tickets_con_error'):
            flash(f'❌ {len(process_result["tickets_con_error"])} tickets con error de procesamiento', 'danger')
        
        if process_result.get('archivo_movido'):
            flash(f'📁 Archivo archivado en processed', 'info')
        elif process_result.get('tickets_insertados', 0) == 0 and not pendientes:
            flash(f'❌ No se insertaron tickets. El archivo queda pendiente para revisión.', 'danger')
        
        # Si hay errores, guardarlos en session
        if process_result.get('errores'):
            session['error_procesamiento'] = {
                'mensaje': process_result.get('message', 'Error en procesamiento'),
                'errores': process_result.get('errores'),
                'tickets_insertados': process_result.get('tickets_insertados', 0)
            }
        
        return redirect(url_for('abm'))
    
    # ========== PROCESAR GET (cargar página) ==========
    # Recuperar pendientes de session (NO hacer pop, mantenerlos hasta que se completen)
    tickets_pendientes = session.get('tickets_pendientes', [])
    error_procesamiento = session.pop('error_procesamiento', None)
    
    # Obtener parámetros de búsqueda
    termino = request.args.get('termino', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    # Construir query para el listado
    query = Ticket.query
    
    if termino:
        query = query.filter(
            db.or_(
                Ticket.paciente.contains(termino),
                Ticket.protocolo.contains(termino),
                Ticket.unidad.contains(termino),
                Ticket.usuario.contains(termino),
                Ticket.pasaje.contains(termino)
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
                         error_procesamiento=error_procesamiento)
    
    
@app.route('/buscar_candidatos', methods=['POST'])
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
        candidates = ticket_processor.processor.protocolo_manager.buscar_candidatos_similares(
            nombre_busqueda=nombre,
            dni_busqueda=dni,
            limit=10
        )
        
        logger.info(f"Se encontraron {len(candidates)} candidatos para ticket_id={ticket_id}")
        return jsonify({'candidates': candidates, 'success': True})
    except Exception as e:
        logger.error(f"Error buscando candidatos: {str(e)}", exc_info=True)
        return jsonify({'error': str(e), 'candidates': [], 'success': False}), 500

@app.route('/seleccionar_paciente', methods=['POST'])
@supabase_helper.login_required
def seleccionar_paciente():
    """Inserta el ticket con el paciente seleccionado manualmente"""
    data = request.get_json()
    ticket_index = data.get('ticket_id')  # Este es el índice del ticket pendiente
    paciente_id = data.get('paciente_id')
    nombre = data.get('nombre')
    apellido = data.get('apellido')
    protocolo = data.get('protocolo')
    nro_doc = data.get('nro_doc')
    usuario = supabase_helper.get_user_display_name(supabase_helper.get_current_user())
    
    logger.info(f"📋 Selección manual de paciente: ticket_index={ticket_index}, paciente='{nombre} {apellido}', protocolo='{protocolo}'")
    
    try:
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

@app.route('/eliminar_pendiente', methods=['POST'])
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

@app.route('/limpiar_uploads_huérfanos')
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

@app.route('/debug/user')
@supabase_helper.login_required
def debug_user():
    user = supabase_helper.get_current_user()
    return jsonify({
        'user': user,
        'user_metadata': user.get('user_metadata', {}),
        'full_name': user.get('full_name'),
        'email': user.get('email')
    })

@app.route('/formulario', methods=['GET', 'POST'])
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
            es_traslado=form.es_traslado.data
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

@app.route('/eliminar_multiples', methods=['POST'])
@supabase_helper.login_required
def eliminar_multiples():
    """Eliminar múltiples tickets seleccionados"""
    ticket_ids = request.form.getlist('ticket_ids')
    
    if not ticket_ids:
        flash('No se seleccionaron tickets para eliminar', 'warning')
        return redirect(url_for('abm'))
    
    success_count = 0
    error_count = 0
    
    for ticket_id in ticket_ids:
        try:
            ticket = Ticket.query.get(int(ticket_id))
            if ticket:
                db.session.delete(ticket)
                success_count += 1
        except Exception as e:
            error_count += 1
            logger.error(f"Error eliminando ticket {ticket_id}: {e}")
    
    try:
        db.session.commit()
        
        if success_count > 0:
            flash(f'Se eliminaron {success_count} ticket(s) correctamente', 'success')
        if error_count > 0:
            flash(f'Error al eliminar {error_count} ticket(s)', 'danger')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar los tickets: {str(e)}', 'danger')
    
    return redirect(url_for('abm'))

@app.route('/listado')
@supabase_helper.login_required
def listado():
    """Listado completo de tickets"""
    user = supabase_helper.get_current_user()
    termino = request.args.get('termino', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    query = Ticket.query
    
    if termino:
        query = query.filter(
            db.or_(
                Ticket.paciente.contains(termino),
                Ticket.protocolo.contains(termino),
                Ticket.pasaje.contains(termino),
                Ticket.usuario.contains(termino)
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

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
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

@app.route('/eliminar/<int:id>')
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

@app.route('/eliminar_con_reintegros/<int:id>', methods=['POST'])
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

@app.route('/procesar/<int:id>', methods=['POST'])
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

@app.route('/buscar')
def buscar():
    termino = request.args.get('termino', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    query = Ticket.query
    
    if termino:
        query = query.filter(
            db.or_(
                Ticket.paciente.contains(termino),
                Ticket.protocolo.contains(termino),
                Ticket.unidad.contains(termino),
                Ticket.usuario.contains(termino)
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

@app.route('/api/tickets')
@supabase_helper.login_required
def api_tickets():
    tickets = Ticket.query.all()
    return jsonify([ticket.to_dict() for ticket in tickets])

@app.route('/api/pacientes/suggestions')
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

@app.route('/api/protocolos/suggestions')
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

@app.route('/superset')
@supabase_helper.login_required
def superset():
    """Vista para embeber dashboard de Superset"""
    guest_token = generate_guest_token(1)
    dashboard_url = f"{SUPERSET_URL}/superset/dashboard/1/?standalone=true&expand_filters=0&guest_token={guest_token}"
    
    return render_template('superset_dashboard.html', 
                         dashboard_url=dashboard_url,
                         guest_token=guest_token,
                         dashboard_id=1,
                         user=supabase_helper.get_current_user())

# =====================================================
# Rutas de Autenticación con Google OAuth
# =====================================================

@app.route('/auth/google')
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

@app.route('/auth/google/callback')
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

@app.route('/auth/logout')
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

@app.route('/admin/crear_usuario', methods=['GET', 'POST'])
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

def init_db():
    """Inicializar esquema de base de datos (search_path + tablas)"""
    with app.app_context():
        esquema = app.config.get('DB_SCHEMA', 'cedir')
        print(f"🔧 Usando esquema de base de datos: {esquema}")
        db.session.execute(text(f"SET search_path TO {esquema}"))
        db.create_all()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5151)