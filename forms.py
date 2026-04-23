from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SubmitField, IntegerField, DecimalField, DateField, SelectField
from wtforms.validators import DataRequired, Length, Optional, NumberRange

# Formulario completo de tickets (si lo necesitas para otra cosa)
class TicketForm(FlaskForm):
    paciente = StringField('Nombre del Paciente', validators=[DataRequired()])
    protocolo = StringField('Protocolo', validators=[DataRequired()])
    # ... otros campos

# Formulario solo para imágenes (el que usamos)
class ImagenForm(FlaskForm):
    imagen = FileField('Cargar Imagen', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'pdf'], 'Solo imágenes y PDF permitidos')
    ])
    submit = SubmitField('Subir Imagen')

class BuscarForm(FlaskForm):
    termino = StringField('Buscar', validators=[Length(max=100)])
    fecha_desde = DateField('Fecha Desde', format='%Y-%m-%d', validators=[Optional()])
    fecha_hasta = DateField('Fecha Hasta', format='%Y-%m-%d', validators=[Optional()])
    submit = SubmitField('Buscar')