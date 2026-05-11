import os
import re
import json
import sqlalchemy as sa
from sqlalchemy import text
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
from PIL import Image
import pdf2image
from typing import Dict, Any, Optional, List
import logging

from tenacity import retry, stop_after_attempt, wait_exponential
from prompt_manager import PromptManager
from protocolo_manager import ProtocoloManager

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TicketProcessor:
    """Procesador de tickets médicos para inserción en base de datos"""
    
    def __init__(self, api_key: str, db_connection_string: str, 
                 processed_folder: str = "processed", prompts_folder: str = "prompts"):
        """
        Inicializa el procesador
        
        Args:
            api_key: API key de Google Gemini
            db_connection_string: String de conexión PostgreSQL
            processed_folder: Carpeta donde mover archivos procesados
            prompts_folder: Carpeta donde están los archivos de prompts
        """
        genai.configure(api_key=api_key)
        
        # Inicializar gestores
        self.prompt_manager = PromptManager(prompts_folder)
        self.engine = sa.create_engine(db_connection_string)
        self.protocolo_manager = ProtocoloManager(self.engine)
        
        # Configuración del modelo
        model_config = self.prompt_manager.get_model_config()
        self.model = genai.GenerativeModel(model_config['model'])
        self.model_config = model_config
        
        self.processed_folder = Path(processed_folder)
        self.processed_folder.mkdir(exist_ok=True)
        
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def extract_from_image(self, image_input, page_num: int = 1, validate: bool = True) -> Dict[str, Any]:
        """Extrae datos del ticket desde una imagen usando Gemini Vision"""

        prompt = self.prompt_manager.get_single_ticket_prompt()

        # Cargar imagen
        if isinstance(image_input, str):
            if image_input.lower().endswith('.pdf'):
                images = pdf2image.convert_from_path(image_input, first_page=page_num, last_page=page_num)
                img = images[0]
            else:
                img = Image.open(image_input)
        elif isinstance(image_input, Image.Image):
            img = image_input
        else:
            raise ValueError("image_input debe ser ruta (str) o objeto PIL Image")

        try:
            # 🔧 FORZAR RESPUESTA JSON PURA
            response = self.model.generate_content(
                [prompt, img],
                generation_config={
                    "response_mime_type": "application/json",  # ← CLAVE: obliga a Gemini a devolver JSON válido
                    "temperature": 0.1,
                    "max_output_tokens": 2048
                }
            )

            raw_response = response.text
            logger.info(f"=== RESPUESTA CRUDA (página {page_num}) ===")
            logger.info(f"Respuesta: {raw_response[:500]}")

            # Ya debería ser JSON puro, pero por seguridad limpiamos
            cleaned_text = self._clean_json_response(raw_response)
            data = json.loads(cleaned_text)

            # Normalizar estructura
            data = self._normalize_ticket_data(data)

            # Validar contra BD
            if validate:
                data = self.protocolo_manager.validate_and_correct_ticket_data(data)
                # Si no encontró al paciente, retornar dict vacío
                encontrado = data.get('paciente', {}).get('encontrado', False)
                logger.info(f"Página {page_num}: paciente encontrado = {encontrado}")

                if not encontrado:
                    logger.warning(f"Página {page_num}: Paciente no encontrado - omitiendo ticket")
                    return None

            return data
            
        except json.JSONDecodeError as e:
            error_file = f"error_response_{page_num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(f"Error: {e}\n\n")
                f.write(f"Respuesta cruda:\n{raw_response}\n\n")
                f.write(f"Texto limpiado:\n{cleaned_text}\n")
            logger.error(f"Respuesta guardada en: {error_file}")
        except Exception as e:
            logger.error(f"Error en página {page_num}: {e}")
            return None
        
    def _normalize_ticket_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza la estructura de datos del ticket"""

        # Si data ya es None o no es dict, intentar recuperar
        if not data:
            logger.warning("Datos vacíos para normalizar")
            return self._get_empty_ticket()

        if not isinstance(data, dict):
            logger.warning(f"Datos no son dict: {type(data)}")
            return self._get_empty_ticket()

        # Estructura por defecto
        normalized = self._get_empty_ticket()

        # Extraer pasaje
        if data.get("pasaje"):
            normalized["pasaje"] = str(data["pasaje"])

        # Extraer fecha_ticket
        if data.get("fecha_ticket"):
            normalized["fecha_ticket"] = data["fecha_ticket"]

        # Extraer paciente
        paciente_data = data.get("paciente", {})
        if isinstance(paciente_data, dict):
            if paciente_data.get("nombre"):
                normalized["paciente"]["nombre"] = paciente_data["nombre"]
            if paciente_data.get("dni"):
                normalized["paciente"]["dni"] = str(paciente_data["dni"])
        elif isinstance(paciente_data, list) and len(paciente_data) > 0:
            if paciente_data[0].get("nombre"):
                normalized["paciente"]["nombre"] = paciente_data[0]["nombre"]
            if paciente_data[0].get("dni"):
                normalized["paciente"]["dni"] = str(paciente_data[0]["dni"])

        # Extraer viaje
        viaje_data = data.get("viaje", {})
        if isinstance(viaje_data, dict):
            normalized["viaje"]["fecha_viaje"] = viaje_data.get("fecha_viaje", "")
            normalized["viaje"]["distancia"] = viaje_data.get("distancia")
            normalized["viaje"]["unidad"] = viaje_data.get("unidad", "")
        elif isinstance(viaje_data, list) and len(viaje_data) > 0:
            normalized["viaje"]["fecha_viaje"] = viaje_data[0].get("fecha_viaje", "")
            normalized["viaje"]["distancia"] = viaje_data[0].get("distancia")
            normalized["viaje"]["unidad"] = viaje_data[0].get("unidad", "")

        # Extraer totales
        totales_data = data.get("totales", {})
        if isinstance(totales_data, dict):
            normalized["totales"]["importe_total"] = totales_data.get("importe_total")
        elif isinstance(totales_data, list) and len(totales_data) > 0:
            normalized["totales"]["importe_total"] = totales_data[0].get("importe_total")

        logger.info(f"Datos normalizados: paciente={normalized['paciente']['nombre']}, "
                    f"importe={normalized['totales']['importe_total']}")

        return normalized

    def _get_empty_ticket(self) -> Dict[str, Any]:
        """Retorna un ticket vacío"""
        return {
            "pasaje": "",
            "fecha_ticket": "",
            "paciente": {"nombre": "", "dni": ""},
            "viaje": {"fecha_viaje": "", "distancia": None, "unidad": ""},
            "totales": {"subtotal": None, "importe_total": None}
        }
    
    def extract_tickets_from_pdf(self, pdf_path: str, validate: bool = True) -> List[Dict[str, Any]]:
        """Extrae múltiples tickets - solo incluye los que tienen paciente encontrado"""

        images = pdf2image.convert_from_path(pdf_path)
        logger.info(f"PDF tiene {len(images)} páginas")

        all_tickets = []

        for page_num, img in enumerate(images, start=1):
            logger.info(f"Procesando página {page_num} de {len(images)}")
            ticket_data = self.extract_from_image(img, page_num, validate=validate)

            if ticket_data:  # Solo agrega si no es None
                all_tickets.append(ticket_data)
            else:
                logger.warning(f"Página {page_num}: Ticket omitido (paciente no encontrado)")

        logger.info(f"Total de tickets válidos: {len(all_tickets)} de {len(images)} páginas")
        return all_tickets

    def generate_insert_sql(self, data: Dict[str, Any], usuario: str = None) -> str:
        """Genera sentencia INSERT - solo se llama si paciente fue encontrado"""

        paciente = data.get('paciente', {})
        viaje = data.get('viaje', {})
        totales = data.get('totales', {})

        # Usar el nombre ya corregido (concatenado de BD)
        nombre = paciente.get('nombre', '')
        protocolo = paciente.get('protocolo', '')

        fecha_viaje = self._convert_date(viaje.get('fecha_viaje', ''))
        fecha_ticket = self._convert_date(data.get('fecha_ticket', ''))
        distancia = viaje.get('distancia')
        unidad = viaje.get('unidad', '')
        importe_total = self._normalize_amount(totales.get('importe_total'))

        pasaje_raw = data.get('pasaje', '')
        pasaje = str(pasaje_raw) if pasaje_raw is not None else ''
        usuario_registro = usuario or 'sistema'

        query = text("""
            INSERT INTO cedir.ticket (
                paciente, fecha_viaje, fecha_ticket, distancia, unidad, 
                protocolo, importe_total, pasaje, create_time, usuario
            ) VALUES (
                :paciente, :fecha_viaje, :fecha_ticket, :distancia, :unidad,
                :protocolo, :importe_total, :pasaje, NOW(), :usuario
            ) RETURNING id
        """)

        params = {
            'paciente': nombre[:150] if nombre else None,
            'fecha_viaje': fecha_viaje,
            'fecha_ticket': fecha_ticket,
            'distancia': distancia,
            'unidad': unidad[:25] if unidad else None,
            'protocolo': protocolo[:100] if protocolo else None,
            'importe_total': importe_total,
            'pasaje': pasaje[:150] if pasaje else None,
            'usuario': usuario_registro[:100] if usuario_registro else None
        }

        compiled = query.bindparams(**params).compile(
            dialect=sa.dialects.postgresql.dialect(),
            compile_kwargs={"literal_binds": True}
        )

        return str(compiled)
    
    def _clean_json_response(self, text: str) -> str:
        """Limpia la respuesta JSON del modelo - versión mejorada"""
        import re

        if not text or not text.strip():
            logger.warning("Respuesta vacía")
            return "{}"

        # Buscar el primer '{' que no esté dentro de texto explicativo
        # Buscar después de '```json' o directamente
        text = text.strip()

        # Eliminar bloques de código markdown
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)

        # Buscar la posición del primer '{'
        start = text.find('{')
        if start == -1:
            # Buscar también como array
            start = text.find('[')

        if start == -1:
            logger.error(f"No se encontró JSON en la respuesta. Respuesta: {text[:200]}")
            return "{}"

        # Buscar el cierre balanceado de llaves
        balance = 0
        end = -1
        in_string = False
        escape = False

        for i, char in enumerate(text[start:], start=start):
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"' and not escape:
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    balance += 1
                elif char == '}':
                    balance -= 1
                    if balance == 0:
                        end = i + 1
                        break
                    
        if end == -1:
            logger.error("No se encontró cierre de JSON")
            return "{}"

        json_text = text[start:end].strip()

        # Limpiar caracteres problemáticos
        json_text = re.sub(r',\s*}', '}', json_text)
        json_text = re.sub(r',\s*]', ']', json_text)
        json_text = re.sub(r'(\d+),(\d+)', r'\1\2', json_text)  # Eliminar comas en números

        # Eliminar BOM
        if json_text.startswith('\ufeff'):
            json_text = json_text[1:]

        logger.info(f"JSON extraído: {json_text[:200]}")

        return json_text
    
    def _extract_with_regex(self, text: str) -> Dict[str, Any]:
        """Extracción básica con regex cuando falla el JSON"""
        data = {
            "pasaje": "",
            "fecha_ticket": "",
            "paciente": [{"nombre": "", "dni": ""}],
            "viaje": [{"fecha_viaje": "", "distancia": None, "unidad": ""}],
            "totales": {
                "subtotal": None,
                "iva": None,
                "otros_tributos": None,
                "importe_total": None
            }
        }
        
        # Extraer fecha del ticket
        fecha_match = re.search(r'fecha_ticket["\']?\s*:\s*["\']([\d/]+)["\']', text)
        if fecha_match:
            data["fecha_ticket"] = fecha_match.group(1)
        
        # Extraer nombre
        nombre_match = re.search(r'nombre["\']?\s*:\s*["\']([^"\']+)["\']', text)
        if nombre_match:
            data["paciente"][0]["nombre"] = nombre_match.group(1)
        
        # Extraer importe total
        total_match = re.search(r'importe_total["\']?\s*:\s*([\d.,]+)', text)
        if total_match:
            total_str = total_match.group(1).replace('.', '').replace(',', '.')
            try:
                data["totales"]["importe_total"] = float(total_str)
            except ValueError:
                pass
        
        return data
    
    def _normalize_amount(self, value: Any) -> Optional[float]:
        """Normaliza montos con formato monetario"""
        if value is None:
            return None

        # Si ya es número
        if isinstance(value, (int, float)):
            return float(value)

        # Si es string
        if isinstance(value, str):
            if not value.strip():
                return None

            # Limpiar el string
            cleaned = value.replace('$', '').replace(' ', '').replace('ARS', '').strip()

            # Manejar formato argentino (punto separador miles, coma decimal)
            if '.' in cleaned and ',' in cleaned:
                # Ejemplo: 15.200,50
                cleaned = cleaned.replace('.', '').replace(',', '.')
            elif ',' in cleaned:
                # Ejemplo: 15200,50
                cleaned = cleaned.replace(',', '.')

            try:
                return float(cleaned)
            except ValueError:
                logger.warning(f"No se pudo convertir el monto: {value}")
                return None

        # Otros tipos (int, float, etc.)
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"No se pudo convertir el monto (tipo {type(value).__name__}): {value}")
            return None
    
    def _convert_date(self, date_str: str) -> Optional[str]:
        """Convierte fecha a formato YYYY-MM-DD"""
        if not date_str:
            return None
        
        # Intentar diferentes formatos
        patterns = [
            (r'(\d{2})/(\d{2})/(\d{4})', lambda m: f"{m[3]}-{m[2]}-{m[1]}"),
            (r'(\d{2})/(\d{2})/(\d{2})', lambda m: f"20{m[3]}-{m[2]}-{m[1]}"),
            (r'(\d{4})-(\d{2})-(\d{2})', lambda m: f"{m[1]}-{m[2]}-{m[3]}"),
        ]
        
        for pattern, formatter in patterns:
            match = re.search(pattern, date_str)
            if match:
                return formatter(match)
        
        return None
    
    def process_multiple_tickets(self, file_path: str, usuario: str = None, 
                              move_to_processed: bool = True, 
                              validate: bool = True) -> Dict[str, Any]:
        """
        Procesa un archivo - solo inserta tickets con paciente encontrado
        """
        logger.info(f"Procesando archivo: {file_path} (usuario: {usuario})")

        result = {
            'success': False,
            'file_path': file_path,
            'usuario': usuario,
            'tickets_procesados': 0,
            'tickets_insertados': 0,
            'tickets_omitidos': 0,
            'tickets': []
        }

        try:
            # Extraer datos (solo los válidos)
            if file_path.lower().endswith('.pdf'):
                tickets_data = self.extract_tickets_from_pdf(file_path, validate=validate)
            else:
                ticket_data = self.extract_from_image(file_path, validate=validate)
                tickets_data = [ticket_data] if ticket_data else []

            result['tickets_procesados'] = len(tickets_data)

            for idx, ticket_data in enumerate(tickets_data, start=1):
                logger.info(f"Insertando ticket {idx} de {len(tickets_data)}")

                # Generar SQL (ya tiene el nombre corregido y protocolo)
                sql_query = self.generate_insert_sql(ticket_data, usuario)
                logger.info(f"SQL para ticket {idx}: {sql_query[:200]}...")

                insert_result = self.insert_ticket(sql_query, file_path)

                ticket_info = {
                    'index': idx,
                    'extracted_data': ticket_data,
                    'insert_result': insert_result
                }

                if insert_result['success']:
                    result['tickets_insertados'] += 1
                    ticket_info['ticket_id'] = insert_result.get('ticket_id')
                else:
                    result['tickets_omitidos'] += 1

                result['tickets'].append(ticket_info)

            result['success'] = result['tickets_insertados'] > 0
            result['message'] = f"Procesados: {result['tickets_insertados']} insertados, {result['tickets_omitidos']} omitidos"

            if move_to_processed:
                processed_path = self.move_to_processed(file_path)
                result['processed_path'] = processed_path

        except Exception as e:
            result['message'] = f'Error en procesamiento: {str(e)}'
            logger.exception("Error procesando archivo")

        return result
    
    def insert_ticket(self, sql_query: str, image_path: str) -> Dict[str, Any]:
        """
        Ejecuta el INSERT en la base de datos con manejo de errores
        
        Args:
            sql_query: Sentencia SQL a ejecutar
            image_path: Ruta de la imagen original
            
        Returns:
            Diccionario con resultado de la operación
        """
        result = {
            'success': False,
            'message': '',
            'sql': sql_query,
            'image_path': image_path
        }
        
        try:
            with self.engine.connect() as conn:
                conn.execute(text(sql_query))
                conn.commit()
            
            result['success'] = True
            result['message'] = 'Ticket insertado correctamente'
            
        except Exception as e:
            result['message'] = f'Error en inserción: {str(e)}'
            logger.error(f"Error ejecutando SQL: {sql_query}\nError: {e}")
            
            # Intentar corregir errores comunes
            corrected_sql = self._correct_sql_errors(sql_query, str(e))
            if corrected_sql != sql_query:
                logger.info(f"SQL corregido: {corrected_sql}")
                try:
                    with self.engine.connect() as conn:
                        conn.execute(text(corrected_sql))
                        conn.commit()
                    result['success'] = True
                    result['message'] = 'Ticket insertado correctamente (con corrección)'
                    result['corrected_sql'] = corrected_sql
                except Exception as e2:
                    result['message'] = f'Error incluso después de corrección: {str(e2)}'
                    result['corrected_sql'] = corrected_sql
        
        return result
    
    def _correct_sql_errors(self, sql: str, error_msg: str) -> str:
        """
        Corrige errores comunes en SQL
        
        Args:
            sql: SQL original
            error_msg: Mensaje de error
            
        Returns:
            SQL corregido
        """
        corrected = sql
        
        # Corregir fechas mal formateadas
        if 'date' in error_msg.lower():
            # Reemplazar fechas en formato DD/MM/YYYY
            corrected = re.sub(
                r"'(\d{2})/(\d{2})/(\d{4})'",
                lambda m: f"'{m.group(3)}-{m.group(2)}-{m.group(1)}'",
                corrected
            )
        
        # Corregir comillas simples escapadas
        corrected = corrected.replace("''", "'")
        
        # Corregir NULL sin comillas
        corrected = re.sub(r"'NULL'", 'NULL', corrected, flags=re.IGNORECASE)
        corrected = re.sub(r'"NULL"', 'NULL', corrected, flags=re.IGNORECASE)
        
        return corrected
    
    def process_ticket(self, image_path: str, move_to_processed: bool = True) -> Dict[str, Any]:
        """
        Proceso completo: extraer -> crear SQL -> insertar -> mover archivo
        
        Args:
            image_path: Ruta de la imagen a procesar
            move_to_processed: Si debe mover el archivo a la carpeta processed
            
        Returns:
            Diccionario con resultado completo del procesamiento
        """
        logger.info(f"Procesando ticket: {image_path}")
        
        result = {
            'success': False,
            'image_path': image_path,
            'steps': {}
        }
        
        try:
            # Paso 1: Extraer datos de la imagen
            logger.info("Extrayendo datos de la imagen...")
            extracted_data = self.extract_from_image(image_path)
            result['steps']['extraction'] = extracted_data
            
            # Paso 2: Generar SQL
            logger.info("Generando SQL...")
            sql_query = self.generate_insert_sql(extracted_data)
            result['steps']['sql'] = sql_query
            
            # Paso 3: Insertar en base de datos
            logger.info("Insertando en base de datos...")
            insert_result = self.insert_ticket(sql_query, image_path)
            result['steps']['insert'] = insert_result
            
            if insert_result['success']:
                result['success'] = True
                result['message'] = insert_result['message']
                
                # Paso 4: Mover archivo a processed
                if move_to_processed:
                    processed_path = self.move_to_processed(image_path)
                    result['processed_path'] = processed_path
            else:
                result['message'] = insert_result['message']
                
        except Exception as e:
            result['message'] = f'Error en procesamiento: {str(e)}'
            logger.exception("Error procesando ticket")
        
        return result
    
    def move_to_processed(self, image_path: str) -> str:
        """
        Mueve el archivo a la carpeta processed con timestamp
        
        Args:
            image_path: Ruta original del archivo
            
        Returns:
            Nueva ruta del archivo
        """
        source = Path(image_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        new_name = f"{timestamp}_{source.name}"
        destination = self.processed_folder / new_name
        
        # Limpiar nombre de caracteres problemáticos
        destination = Path(str(destination).replace(' ', '_').replace('(', '').replace(')', ''))
        
        source.rename(destination)
        logger.info(f"Archivo movido a: {destination}")
        
        return str(destination)


# Módulo para integración con Flask
class FlaskTicketProcessor:
    """Wrapper para integrar el procesador con Flask"""
    
    def __init__(self, app=None):
        self.processor = None
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Inicializa con la configuración de Flask"""
        api_key = app.config.get('GEMINI_API_KEY')
        db_url = app.config.get('DATABASE_URL')
        processed_folder = app.config.get('PROCESSED_FOLDER', 'processed')
        prompts_folder = app.config.get('PROMPTS_FOLDER', 'prompts')
        
        if not api_key or not db_url:
            raise ValueError("Faltan configuraciones: GEMINI_API_KEY y DATABASE_URL")
        
        self.processor = TicketProcessor(api_key, db_url, processed_folder, prompts_folder)
        app.ticket_processor = self
    
    def process_uploaded_file(self, file_path: str, usuario: str = None, 
                               move_to_processed: bool = True, 
                               validate_protocolo: bool = True) -> Dict[str, Any]:
        """Procesa un archivo subido
        
        Args:
            file_path: Ruta del archivo
            usuario: Nombre del usuario logueado (full_name)
            move_to_processed: Si mover a processed
            validate_protocolo: Si validar protocolos
        """
        if not self.processor:
            raise RuntimeError("Procesador no inicializado")
        
        return self.processor.process_multiple_tickets(file_path, usuario, move_to_processed, validate_protocolo)
    
    def get_protocolo_suggestions(self, partial: str, limit: int = 10) -> List[str]:
        """Obtiene sugerencias de protocolo para autocompletar"""
        if not self.processor:
            return []
        return self.processor.protocolo_manager.get_protocolo_suggestions(partial, limit)
    
    def get_all_protocolos(self) -> List[str]:
        """Obtiene todos los protocolos disponibles"""
        if not self.processor:
            return []
        return self.processor.protocolo_manager.get_all_protocolos()