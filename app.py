import os
import jwt
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from werkzeug.utils import secure_filename
from config import Config
from models import db, Ticket
import supabase_helper  # Importar el módulo
from forms import TicketForm, BuscarForm, ImagenForm
import requests
from urllib.parse import urlencode

app = Flask(__name__)
app.config.from_object(Config)

# Configuración de Superset
SUPERSET_URL = "http://192.168.37.182:8088"
GUEST_TOKEN_JWT_SECRET = "3c7c2f380ee1e034889c7bb263d2f6850cde8a8a4151c0c4f8b2ef1f30e897e2"
GUEST_TOKEN_JWT_ALGO = "HS256"

def generate_guest_token(dashboard_id, user_info=None):
    """
    Genera un token guest para embeder dashboards de Superset sin autenticación
    """
    if user_info is None:
        user_info = {
            "username": "guest_user",
            "first_name": "Guest",
            "last_name": "User"
        }
    
    # Calcular expiración
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
    
    # Procesar la carga de imagen
    if form.validate_on_submit():
        if form.imagen.data and form.imagen.data.filename:
            file = form.imagen.data
            if file and allowed_file(file.filename):
                try:
                    filename = secure_filename(file.filename)
                    import time
                    timestamp = int(time.time())
                    filename = f"{timestamp}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                    file.save(filepath)
                    
                    if os.path.exists(filepath):
                        # Guardar referencia en la base de datos
                        ticket = Ticket(
                            imagen_path=f"uploads/{filename}",
                            create_time=datetime.utcnow(),
                            usuario=user['email']
                        )
                        db.session.add(ticket)
                        db.session.commit()
                        
                        file_size = os.path.getsize(filepath)
                        flash(f'¡Imagen cargada exitosamente! (ID: {ticket.id})', 'success')
                    else:
                        flash('Error: No se pudo verificar la imagen guardada', 'danger')
                        
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error al guardar la imagen: {str(e)}', 'danger')
            else:
                flash('Formato de archivo no permitido', 'danger')
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

@app.route('/formulario', methods=['GET', 'POST'])
def formulario():
    form = TicketForm()
    
    if form.validate_on_submit():
        # Procesar imagen
        imagen_path = None
        if form.imagen.data and form.imagen.data.filename:
            file = form.imagen.data
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                import time
                filename = f"{int(time.time())}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                imagen_path = f"uploads/{filename}"
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
            imagen_path=imagen_path,
            create_time=datetime.utcnow()
        )
        
        try:
            db.session.add(ticket)
            db.session.commit()
            flash('Ticket guardado exitosamente', 'success')
            return redirect(url_for('listado'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar: {str(e)}', 'danger')
    
    return render_template('formulario.html', form=form)


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
    
    if form.validate_on_submit():
        ticket.pasaje = form.pasaje.data
        ticket.paciente = form.paciente.data
        ticket.fecha_viaje = form.fecha_viaje.data
        ticket.fecha_ticket = form.fecha_ticket.data
        ticket.distancia = form.distancia.data
        ticket.unidad = form.unidad.data
        ticket.protocolo = form.protocolo.data
        ticket.subtotal = form.subtotal.data
        ticket.importe_total = form.importe_total.data
        ticket.usuario = user['email']
        
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
            return redirect(url_for('listado'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')
    
    return render_template('editar.html', form=form, ticket=ticket, user=user)

""" @app.route('/abm', methods=['GET', 'POST'])
def abm():
    
    form = ImagenForm()
    
    # Procesar la carga de imagen (SOLO GUARDA EN CARPETA)
    if form.validate_on_submit():
        if form.imagen.data and form.imagen.data.filename:
            file = form.imagen.data
            if file and allowed_file(file.filename):
                try:
                    # Crear nombre único para el archivo
                    filename = secure_filename(file.filename)
                    import time
                    timestamp = int(time.time())
                    filename = f"{timestamp}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                    # Guardar la imagen en el servidor
                    file.save(filepath)
                    
                    # Verificar que el archivo se guardó correctamente
                    if os.path.exists(filepath):
                        # Obtener tamaño del archivo
                        file_size = os.path.getsize(filepath)
                        flash(f'¡Imagen cargada exitosamente! ({filename}) - Tamaño: {file_size} bytes', 'success')
                    else:
                        flash('Error: No se pudo verificar la imagen guardada', 'danger')
                        
                except Exception as e:
                    flash(f'Error al guardar la imagen: {str(e)}', 'danger')
            else:
                flash('Formato de archivo no permitido. Use: JPG, PNG, GIF, BMP, PDF', 'danger')
        else:
            flash('No se seleccionó ningún archivo', 'warning')
        
        return redirect(url_for('abm'))
    
    # Obtener lista de archivos de la carpeta uploads (para mostrar en el listado)
    imagenes = []
    upload_folder = app.config['UPLOAD_FOLDER']
    
    if os.path.exists(upload_folder):
        for filename in os.listdir(upload_folder):
            filepath = os.path.join(upload_folder, filename)
            if os.path.isfile(filepath):
                # Obtener información del archivo
                stat = os.stat(filepath)
                imagenes.append({
                    'nombre': filename,
                    'ruta': f"uploads/{filename}",
                    'tamaño': stat.st_size,
                    'fecha': datetime.fromtimestamp(stat.st_mtime),
                    'extension': filename.split('.')[-1].upper() if '.' in filename else 'DESCONOCIDO'
                })
    
    # Ordenar por fecha descendente (más recientes primero)
    imagenes.sort(key=lambda x: x['fecha'], reverse=True)
    
    # Filtrar por término de búsqueda si existe
    termino = request.args.get('termino', '')
    if termino:
        imagenes = [img for img in imagenes if termino.lower() in img['nombre'].lower()]
    
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
                         imagenes=imagenes, 
                         tickets=tickets,
                         termino=termino) """

@app.route('/eliminar_imagen/<filename>')
def eliminar_imagen(filename):
    """Eliminar una imagen de la carpeta uploads"""
    try:
        # Construir la ruta completa del archivo
        filepath = os.path.join(app.config['PROCESSED_FOLDER'], filename)
        
        # Verificar que el archivo existe
        if os.path.exists(filepath):
            os.remove(filepath)
            flash(f'Imagen "{filename}" eliminada exitosamente', 'success')
        else:
            flash(f'La imagen "{filename}" no existe', 'warning')
            
    except Exception as e:
        flash(f'Error al eliminar la imagen: {str(e)}', 'danger')
    
    return redirect(url_for('abm'))

@app.route('/eliminar/<int:id>')
@supabase_helper.login_required
def eliminar(id):
    """Eliminar ticket"""
    ticket = Ticket.query.get_or_404(id)
    
    if ticket.imagen_path:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                 os.path.basename(ticket.imagen_path))
        if os.path.exists(image_path):
            os.remove(image_path)
    
    try:
        db.session.delete(ticket)
        db.session.commit()
        flash('Ticket eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
    
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

@app.route('/superset')
def superset():
    """Vista para embeber un dashboard específico de Superset"""
    # Generar token guest para el dashboard
    guest_token = generate_guest_token(1)
    
    # Construir URL de embed con el token
    # Usamos el endpoint de embed en lugar del dashboard normal
    embed_url = f"{SUPERSET_URL}/api/v1/security/guest_token/?token={guest_token}"
    
    # Método alternativo: Usar el iframe directamente
    dashboard_url = f"{SUPERSET_URL}/superset/dashboard/1/?standalone=true"
    
    return render_template('superset_dashboard.html', 
                         dashboard_url=dashboard_url,
                         guest_token=guest_token,
                         dashboard_id=1)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)