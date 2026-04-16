from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SubmitField, IntegerField, DecimalField, DateField, SelectField
from wtforms.validators import DataRequired, Length, Optional, NumberRange

class TicketForm(FlaskForm):
    pasaje = StringField('Código de pasaje', validators=[
        Optional(),
        Length(max=150, message='Máximo 150 caracteres')
    ])
    
    paciente = StringField('Nombre del Paciente', validators=[
        DataRequired(message='El nombre del paciente es requerido'),
        Length(max=150, message='Máximo 150 caracteres')
    ])
    
    fecha_viaje = DateField('Fecha de Viaje', format='%Y-%m-%d', validators=[Optional()])
    
    fecha_ticket = DateField('Fecha del Ticket', format='%Y-%m-%d', validators=[Optional()])
    
    distancia = IntegerField('Distancia', validators=[
        Optional(),
        NumberRange(min=0, message='La distancia debe ser positiva')
    ])
    
    unidad = StringField('Unidad de medida', validators=[
        Optional(),
        Length(max=50, message='Máximo 50 caracteres')
    ])
    
    protocolo = StringField('Protocolo', validators=[
        DataRequired(message='El protocolo es requerido'),
        Length(max=100, message='Máximo 100 caracteres')
    ])
    
    subtotal = DecimalField('Subtotal', places=2, validators=[Optional()])
    
    importe_total = DecimalField('Importe Total', places=2, validators=[Optional()])
    
    usuario = StringField('Usuario', validators=[
        DataRequired(message='El usuario es requerido'),
        Length(max=100, message='Máximo 100 caracteres')
    ])
    
    imagen = FileField('Imagen del Ticket', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'pdf'], 'Solo imágenes y PDF permitidos')
    ])
    
    submit = SubmitField('Guardar Ticket')

class BuscarForm(FlaskForm):
    termino = StringField('Buscar', validators=[Length(max=100)])
    fecha_desde = DateField('Fecha Desde', format='%Y-%m-%d', validators=[Optional()])
    fecha_hasta = DateField('Fecha Hasta', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('Buscar')