from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import BooleanField, StringField, SubmitField, IntegerField, DecimalField, DateField, SelectField
from wtforms.validators import DataRequired, Length, Optional, NumberRange

# Formulario COMPLETO para EDICIÓN (todos los campos)
class TicketForm(FlaskForm):
    pasaje = StringField('Número de Pasaje', validators=[Optional(), Length(max=150)])
    
    paciente = StringField('Nombre del Paciente', validators=[
        DataRequired(message='El nombre del paciente es requerido'),
        Length(max=150)
    ])
    
    fecha_viaje = DateField('Fecha de Viaje', format='%Y-%m-%d', validators=[Optional()])
    
    fecha_ticket = DateField('Fecha del Ticket', format='%Y-%m-%d', validators=[Optional()])
    
    distancia = IntegerField('Distancia (km)', validators=[
        Optional(),
        NumberRange(min=0, message='La distancia debe ser positiva')
    ])
    
    unidad = StringField('Unidad', validators=[Optional(), Length(max=150)])
    
    protocolo = StringField('Protocolo', validators=[
        DataRequired(message='El protocolo es requerido'),
        Length(max=100, message='Máximo 100 caracteres')
    ])
    
    tipo_visita = SelectField('Tipo de Visita', choices=[
        ('', 'Seleccionar...'),
        ('V1',	'Visita basal / Screening'),
        ('V2',	'Visita de randomización'),
        ('V3-Vn',	'Visitas de seguimiento'),
        ('V601',	'Visita de fin de estudio / cierre'),
        ('PDTV',	'Visita de discontinuación temprana'),
        ('FV',	'Visita final'),
        ('EMV',	'Visita de fin de estudio (End of Study)'),
        ('OTRA','Otra')
    ], validators=[Optional()])
    
    requiere_cuidador = BooleanField('Requiere Cuidador', default=False)
    
    es_contingencia = BooleanField('Es Contingencia', default=False)
    
    horas_duracion_visita = DecimalField('Horas de Duración de la Visita', 
                                          places=2, 
                                          validators=[Optional(), NumberRange(min=0, max=24)])
    
    cantidad_comidas = IntegerField('Cantidad de Comidas', 
                                    default=1,
                                    validators=[Optional(), NumberRange(min=0, max=10)])
    
    cantidad_noches = IntegerField('Cantidad de Noches', 
                                   default=0,
                                   validators=[Optional(), NumberRange(min=0, max=30)])
    
    preseleccion_no_completo = BooleanField('Preselección No Completa', default=False)
    
    subtotal = DecimalField('Subtotal', places=2, validators=[Optional()])
    
    importe_total = DecimalField('Importe Total', places=2, validators=[Optional()])

    
    imagen = FileField('Imagen del Ticket', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'pdf'], 'Solo imágenes y PDF permitidos')
    ])
    
    submit = SubmitField('Guardar Cambios')

# Formulario SOLO para carga rápida de imágenes
class ImagenForm(FlaskForm):
    imagen = FileField('Cargar Imagen', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'pdf'], 'Solo imágenes y PDF permitidos')
    ])
    submit = SubmitField('Subir Imagen')

# Formulario para búsqueda
class BuscarForm(FlaskForm):
    termino = StringField('Buscar', validators=[Length(max=100)])
    fecha_desde = DateField('Fecha Desde', format='%Y-%m-%d', validators=[Optional()])
    fecha_hasta = DateField('Fecha Hasta', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('Buscar')