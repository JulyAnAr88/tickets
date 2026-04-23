from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Ticket(db.Model):
    __tablename__ = 'ticket'
    __table_args__ = {'schema': 'cedir'}
    
    id = db.Column(db.Integer, primary_key=True)
    paciente = db.Column(db.String(150), nullable=True)
    fecha_viaje = db.Column(db.Date, nullable=True)
    fecha_ticket = db.Column(db.Date, nullable=True)
    distancia = db.Column(db.Integer, nullable=True)
    unidad = db.Column(db.String(25), nullable=True)
    protocolo = db.Column(db.String(100), nullable=True)
    subtotal = db.Column(db.Numeric(38, 2), nullable=True)
    importe_total = db.Column(db.Numeric(38, 2), nullable=True)
    forma_pago = db.Column(db.String, nullable=True)  # Nuevo campo
    pasaje = db.Column(db.String(150), nullable=True)  # Nuevo campo
    create_time = db.Column(db.DateTime, default=datetime.utcnow)
    usuario = db.Column(db.String(100), nullable=True)
    imagen_path = db.Column(db.String(500), nullable=True)
    
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
            'forma_pago': self.forma_pago,
            'pasaje': self.pasaje,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'usuario': self.usuario,
            'imagen_path': self.imagen_path
        }