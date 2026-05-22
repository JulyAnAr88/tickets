import os
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

load_dotenv()
DB_SCHEMA = os.environ.get('DB_SCHEMA', 'cedir')

db = SQLAlchemy()

class Ticket(db.Model):
    __tablename__ = 'ticket'
    __table_args__ = {'schema': DB_SCHEMA}
    
    id = db.Column(db.Integer, primary_key=True)
    paciente = db.Column(db.String(150), nullable=True)
    fecha_viaje = db.Column(db.Date, nullable=True)
    fecha_ticket = db.Column(db.Date, nullable=True)
    distancia = db.Column(db.Integer, nullable=True)
    unidad = db.Column(db.String(25), nullable=True)
    protocolo = db.Column(db.String(100), nullable=True)
    subtotal = db.Column(db.Numeric(38, 2), nullable=True)
    importe_total = db.Column(db.Numeric(38, 2), nullable=True)
    pasaje = db.Column(db.String(150), nullable=True)  # Nuevo campo
    create_time = db.Column(db.DateTime, default=datetime.utcnow)
    usuario = db.Column(db.String(100), nullable=True)
    tipo_visita = db.Column(db.String(50), nullable=True)
    requiere_cuidador = db.Column(db.Boolean, default=False)
    es_contingencia = db.Column(db.Boolean, default=False)
    horas_duracion_visita = db.Column(db.Numeric(5, 2), nullable=True)
    cantidad_comidas = db.Column(db.Integer, default=1)
    cantidad_noches = db.Column(db.Integer, default=0)
    preseleccion_no_completo = db.Column(db.Boolean, default=False)
    id_paciente = db.Column(db.Integer, nullable=True)
    
    def __repr__(self):
        return f'<Ticket {self.id} - {self.paciente}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'paciente': self.paciente,
            'fecha_viaje': self.fecha_viaje.strftime('%Y-%m-%d') if self.fecha_viaje else None,
            'fecha_ticket': self.fecha_ticket.strftime('%Y-%m-%d') if self.fecha_ticket else None,
            'distancia': self.distancia,
            'unidad': self.unidad,
            'protocolo': self.protocolo,
            'subtotal': float(self.subtotal) if self.subtotal else None,
            'importe_total': float(self.importe_total) if self.importe_total else None,
            'pasaje': self.pasaje,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'usuario': self.usuario,
            'tipo_visita': self.tipo_visita,
            'requiere_cuidador': self.requiere_cuidador,
            'es_contingencia': self.es_contingencia,
            'horas_duracion_visita': float(self.horas_duracion_visita) if self.horas_duracion_visita else None,
            'cantidad_comidas': self.cantidad_comidas,
            'cantidad_noches': self.cantidad_noches,
            'preseleccion_no_completo': self.preseleccion_no_completo,
            'id_paciente': self.id_paciente
        }