import os
import jwt
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from werkzeug.utils import secure_filename
from config import Config
from models import db, Ticket
import supabase_helper
from forms import TicketForm, BuscarForm, ImagenForm
from ticket_processor import FlaskTicketProcessor
import requests
from urllib.parse import urlencode
import logging

app = Flask(__name__)
app.config.from_object(Config)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inicializar procesador de tickets
try:
    ticket_processor = FlaskTicketProcessor(app)
    print("✅ Procesador de tickets inicializado correctamente")
except Exception as e:
    print(f"⚠️ Error inicializando procesador de tickets: {e}")
    ticket_processor = None

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

# ============ RUTAS DE AUTENTICACIÓN ============

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de inicio de sesión"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        result = supabase_helper.sign_in_user(email, password)
        
        if result['success']:
            flash(result['message'], 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('abm'))
        else:
            flash(result['message'], 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
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

    # Obtener nombre del usuario para guardar
    nombre_usuario = supabase_helper.get_user_display_name(user)
    
    # Procesar la carga de imagen
    if form.validate_on_submit():
        if form.imagen.data and form.imagen.data.filename:
            file = form.imagen.data
            filename = file.filename
            logger.info(f"Archivo recibido: {filename}")
            logger.info(f"Extensión: {filename.split('.')[-1].lower()}")
            logger.info(f"Extensiones permitidas: {app.config['ALLOWED_EXTENSIONS']}")
            if file and allowed_file(file.filename):
                try:
                    filename = secure_filename(file.filename)                    
                    filename = f"{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                                        # Guardar la imagen temporalmente
                    file.save(filepath)
                    
                    if os.path.exists(filepath):
                        # Procesar el ticket con Gemini
                        if ticket_processor:
                            flash('Procesando imagen con IA...', 'info')
                            process_result = ticket_processor.process_uploaded_file(filepath, move_to_processed=True)
                            
                            if process_result['success']:
                                flash(f'✅ {process_result["message"]}', 'success')
                                
                                # Mostrar datos extraídos en un modal o collapsible
                                if 'steps' in process_result and 'extraction' in process_result['steps']:
                                    extracted = process_result['steps']['extraction']
                                    flash(f'📊 Datos extraídos: {extracted}', 'info')
                            else:
                                flash(f'⚠️ El archivo se guardó pero hubo error en procesamiento: {process_result["message"]}', 'warning')
                                
                                # Guardar solo la imagen si falla el procesamiento
                                ticket = Ticket(
                                    create_time=datetime.utcnow(),
                                    usuario=nombre_usuario
                                )
                                db.session.add(ticket)
                                db.session.commit()
                                flash('La imagen fue guardada y será procesada manualmente más tarde', 'info')
                        else:
                            # Si no hay procesador, solo guardar la imagen
                            ticket = Ticket(
                                create_time=datetime.utcnow(),
                                usuario=nombre_usuario
                            )
                            db.session.add(ticket)
                            db.session.commit()
                            flash('Imagen guardada (procesamiento no disponible)', 'warning')
                    else:
                        flash('Error: No se pudo guardar la imagen', 'danger')
                        
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error al procesar: {str(e)}', 'danger')
            else:
                flash('Formato de archivo no permitido.Extensiones permitidas: {", ".join(app.config["ALLOWED_EXTENSIONS"])}', 'danger')
        else:
            flash('No se seleccionó ningún archivo', 'warning')
        
        return redirect(url_for('abm'))
    
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
                         user=user)

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
def formulario():
    form = TicketForm()
    
    if form.validate_on_submit():
        # Procesar imagen
        if form.imagen.data and form.imagen.data.filename:
            file = form.imagen.data
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                import time
                filename = f"{int(time.time())}_{filename}"
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
            create_time=datetime.utcnow()
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
                filename = f"{int(time.time())}_{filename}"
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
    """Eliminar ticket"""
    ticket = Ticket.query.get_or_404(id)
    
    try:
        db.session.delete(ticket)
        db.session.commit()
        flash('Ticket eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    
    return redirect(url_for('abm'))

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
    dashboard_url = f"{SUPERSET_URL}/superset/dashboard/1/?standalone=true&guest_token={guest_token}"
    
    return render_template('superset_dashboard.html', 
                         dashboard_url=dashboard_url,
                         guest_token=guest_token,
                         dashboard_id=1,
                         user=supabase_helper.get_current_user())

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5151)