import os
import jwt
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from werkzeug.utils import secure_filename
from config import Config
from models import db, Ticket

from forms import BuscarForm, ImagenForm  # Agrega ImagenForm a los imports
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

# Crear carpeta de uploads si no existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.after_request
def add_header(response):
    """Agregar headers para permitir embebidos"""
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    response.headers['Content-Security-Policy'] = "frame-ancestors *"
    return response

@app.route('/')
def index():
    return render_template('index.html')

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
def listado():
    tickets = Ticket.query.order_by(Ticket.create_time.desc()).all()
    return render_template('listado.html', tickets=tickets)

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    ticket = Ticket.query.get_or_404(id)
    form = TicketForm(obj=ticket)
    
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
        ticket.usuario = form.usuario.data
        
        # Procesar nueva imagen si se subió
        if form.imagen.data and form.imagen.data.filename:
            file = form.imagen.data
            if file and allowed_file(file.filename):
                # Eliminar imagen anterior si existe
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
    
    return render_template('formulario.html', form=form, ticket=ticket)


@app.route('/abm', methods=['GET', 'POST'])
def abm():
    """Página unificada con carga de imágenes y listado de tickets"""
    form = ImagenForm()  # Usar el formulario solo de imagen
    
    # Procesar la carga de imagen
    if form.validate_on_submit():
        if form.imagen.data and form.imagen.data.filename:
            file = form.imagen.data
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                import time
                filename = f"{int(time.time())}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                imagen_path = f"uploads/{filename}"
                
                # Crear un nuevo ticket SOLO con la imagen (otros campos vacíos)
                ticket = Ticket(
                    paciente=None,
                    fecha_viaje=None,
                    fecha_ticket=None,
                    distancia=None,
                    unidad=None,
                    protocolo=None,
                    subtotal=None,
                    importe_total=None,
                    forma_pago=None,
                    pasaje=None,
                    usuario="sistema",  # Usuario por defecto
                    imagen_path=imagen_path,
                    create_time=datetime.utcnow()
                )
                
                try:
                    db.session.add(ticket)
                    db.session.commit()
                    flash('Imagen cargada exitosamente', 'success')
                    return redirect(url_for('abm'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error al guardar: {str(e)}', 'danger')
            else:
                flash('Formato de archivo no permitido', 'danger')
    
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
                         fecha_hasta=fecha_hasta)

# Mantener la ruta de eliminar igual
@app.route('/eliminar/<int:id>')
def eliminar(id):
    ticket = Ticket.query.get_or_404(id)
    
    # Eliminar imagen asociada
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