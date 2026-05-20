import os
import re
import json
import logging
import numpy as np
import base64
import requests
from unittest import result
import sqlalchemy as sa
from sqlalchemy import text
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
from PIL import Image

# Importaciones para OCR local
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logging.warning("Tesseract no disponible")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logging.warning("OpenCV no disponible")
import pdf2image
from typing import Dict, Any, Optional, List
import logging
import traceback
from datetime import datetime
import traceback 

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
        """Extrae datos del ticket - SIEMPRE retorna un diccionario, nunca lanza excepción"""

        prompt = self.prompt_manager.get_single_ticket_prompt()

        # Cargar imagen
        if isinstance(image_input, str):
            if image_input.lower().endswith('.pdf'):
                try:
                    images = pdf2image.convert_from_path(image_input, first_page=page_num, last_page=page_num)
                    img = images[0]
                except Exception as e:
                    logger.error(f"Error cargando PDF página {page_num}: {e}")
                    return self._get_error_ticket(page_num, f"Error cargando PDF: {str(e)}")
            else:
                try:
                    img = Image.open(image_input)
                except Exception as e:
                    logger.error(f"Error cargando imagen página {page_num}: {e}")
                    return self._get_error_ticket(page_num, f"Error cargando imagen: {str(e)}")
        elif isinstance(image_input, Image.Image):
            img = image_input
        else:
            return self._get_error_ticket(page_num, "Formato de imagen no válido")

        try:
            # =====================================================
            # 🔄 MÉTODO HÍBRIDO: n8n → Gemini → Tesseract
            # =====================================================
            
            # 1°: n8n webhook (primero)
            logger.info(f"🔍 Intentando con n8n webhook (página {page_num})...")
            data = self._extract_with_n8n(image_input, page_num)
            
            tiene_importe = False
            tiene_paciente = False
            
            if data and not data.get('_error'):
                importe = data.get('totales', {}).get('importe_total')
                nombre = data.get('paciente', {}).get('nombre', '')
                dni = data.get('paciente', {}).get('dni', '')
                
                if importe and float(importe) > 0:
                    tiene_importe = True
                    logger.info(f"✅ n8n detectó importe: ${importe}")
                if nombre or dni:
                    tiene_paciente = True
                    logger.info(f"✅ n8n detectó paciente: {nombre} / DNI: {dni}")
            
            # 2°: Si no detectó datos, intentar con Gemini
            if not tiene_importe and not tiene_paciente:
                logger.info("🤖 n8n no detectó datos. Intentando con Gemini...")
                try:
                    response = self.model.generate_content(
                        [prompt, img],
                        generation_config={
                            "response_mime_type": "application/json",
                            "temperature": 0.0,
                            "max_output_tokens": 2048
                        }
                    )
                    raw_response = response.text
                    logger.info(f"=== RESPUESTA CRUDA IA (página {page_num}) ===")
                    logger.info(f"Respuesta: {raw_response[:500]}")

                    cleaned_text = self._clean_json_response(raw_response)
                    data = json.loads(cleaned_text)
                    data = self._normalize_ticket_data(data)
                    
                    if data and not self._es_dato_placeholder(data):
                        importe = data.get('totales', {}).get('importe_total') or data.get('importe_total')
                        nombre = data.get('paciente', {}).get('nombre', '')
                        dni = data.get('paciente', {}).get('dni', '')
                        
                        if importe and float(importe) > 0:
                            tiene_importe = True
                            logger.info(f"✅ Gemini detectó importe: ${importe}")
                        if nombre or dni:
                            tiene_paciente = True
                            logger.info(f"✅ Gemini detectó paciente: {nombre} / DNI: {dni}")
                        logger.info("✅ Extracción con Gemini exitosa")
                except Exception as e:
                    logger.warning(f"⚠️ Error con Gemini: {e}")
            
            # 3°: Si sigue sin detectar, usar Tesseract
            if not tiene_importe and not tiene_paciente:
                logger.info("🔄 Ni n8n ni Gemini detectaron datos. Usando Tesseract...")
                data = self._extract_with_ocr_local(image_input, page_num)
            elif data and validate:
                # Si tenemos datos pero validamos, procesamos
                data = self.protocolo_manager.validate_and_correct_ticket_data(data)
            
            # Si no hay datos, usar OCR local como respaldo
            if not data or (not data.get('totales', {}).get('importe_total') and not data.get('paciente', {}).get('nombre')):
                logger.info("🔄 Usando OCR local como respaldo...")
                data = self._extract_with_ocr_local(image_input, page_num)

            if validate and data and not data.get('_error'):
                data = self.protocolo_manager.validate_and_correct_ticket_data(data)
                
                # =====================================================
                # 📋 LOG COMPLETO DE DATOS EXTRAÍDOS DEL TICKET
                # =====================================================
                logger.info("=" * 60)
                logger.info(f"📋 DATOS EXTRAÍDOS DEL TICKET (página {page_num})")
                logger.info("=" * 60)
                
                # Paciente
                paciente = data.get('paciente', {})
                logger.info(f"👤 PACIENTE:")
                logger.info(f"   - Nombre: {paciente.get('nombre', 'N/A')}")
                logger.info(f"   - Apellido: {paciente.get('apellido', 'N/A')}")
                logger.info(f"   - DNI: {paciente.get('dni', 'N/A')}")
                logger.info(f"   - Encontrado: {paciente.get('encontrado', False)}")
                logger.info(f"   - Protocolo: {paciente.get('protocolo', 'N/A')}")
                
                # Viaje
                viaje = data.get('viaje', {})
                logger.info(f"🚗 VIAJE:")
                logger.info(f"   - Fecha: {viaje.get('fecha_viaje', 'N/A')}")
                logger.info(f"   - Distancia: {viaje.get('distancia', 'N/A')} {viaje.get('unidad', '')}")
                logger.info(f"   - Desde: {viaje.get('desde', 'N/A')}")
                logger.info(f"   - Hasta: {viaje.get('hasta', 'N/A')}")
                
                # Totales
                totales = data.get('totales', {})
                logger.info(f"💰 TOTALES:")
                logger.info(f"   - Importe total: ${totales.get('importe_total', 'N/A')}")
                logger.info(f"   - Importe passagem: ${totales.get('importe_pasaje', 'N/A')}")
                logger.info(f"   - Importe peaje: ${totales.get('importe_peaje', 'N/A')}")
                
                # Pasaje
                logger.info(f"🎫 PASAJE:")
                logger.info(f"   - Pasaje: {data.get('pasaje', 'N/A')}")
                
                # Fecha ticket
                logger.info(f"📅 FECHA TICKET: {data.get('fecha_ticket', 'N/A')}")
                logger.info("=" * 60)
                
                encontrado = data.get('paciente', {}).get('encontrado', False)
                requiere_seleccion = data.get('paciente', {}).get('requiere_seleccion', False)
                
                logger.info(f"Página {page_num}: paciente encontrado = {encontrado}, requiere_seleccion = {requiere_seleccion}")
                
                if not encontrado:
                    data['_requiere_seleccion'] = True
                    data['_insertar'] = False
                else:
                    data['_requiere_seleccion'] = False
                    data['_insertar'] = True
            
            return data
             
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error en página {page_num}: {error_msg}")

            # 🔥 RETORNAR UN TICKET CON ERROR, NO LANZAR EXCEPCIÓN
            return self._get_error_ticket(page_num, error_msg)
    
    def _es_dato_placeholder(self, data: Dict[str, Any]) -> bool:
        """
        Verifica si los datos devueltos por la IA son placeholders/genéricos
        Ejemplo: "nombre apellido", "número", etc.
        """
        if not data:
            return True
        
        # Lista de valores que indican placeholder
        placeholders_nombre = [
            'nombre apellido', 'nombre y apellido', 'nombre completo',
            'nombre y appelido', 'nombre del pasajero', 'cliente',
            'pasajero', 'beneficiario', 'titular'
        ]
        
        placeholders_dni = [
            'número', 'numero', 'dni', 'documento', 'nro', 'num',
            '12345678', '00000000', '11111111'
        ]
        
        placeholders_importe = ['0', 0, '0.00', 0.0, None, '']
        
        # Verificar nombre
        nombre = data.get('paciente', {}).get('nombre', '')
        if nombre:
            nombre_lower = nombre.lower().strip()
            if nombre_lower in placeholders_nombre or len(nombre_lower) < 3:
                logger.warning(f"⚠️ Nombre parece ser placeholder: '{nombre}'")
                return True
        
        # Verificar DNI
        dni = data.get('paciente', {}).get('dni', '')
        if dni:
            dni_lower = str(dni).lower().strip()
            if dni_lower in placeholders_dni or dni_lower.isdigit() and int(dni_lower) < 1000000:
                logger.warning(f"⚠️ DNI parece ser placeholder: '{dni}'")
                return True
        
        # Verificar importe
        importe = data.get('totales', {}).get('importe_total') or data.get('importe_total')
        if not importe or importe in placeholders_importe:
            logger.warning(f"⚠️ Importe parece ser placeholder: '{importe}'")
            return False  # El importe puede ser 0, no significa que sea placeholder
        
        return False
    
    def _extract_with_n8n(self, image_input, page_num: int = 1) -> Dict[str, Any]:
        """
        Extrae datos enviando la imagen a un webhook de n8n
        """
        logger.info(f"🔍 Enviando a n8n OCR para página {page_num}...")
        
        webhook_url = os.environ.get('N8N_OCR_WEBHOOK_URL', '')
        if not webhook_url:
            logger.warning("N8N_OCR_WEBHOOK_URL no configurada")
            return self._get_error_ticket(page_num, "n8n webhook no configurado")
        
        try:
            # Cargar imagen
            if isinstance(image_input, str):
                if image_input.lower().endswith('.pdf'):
                    from pdf2image import convert_from_path
                    images = convert_from_path(image_input, first_page=page_num, last_page=page_num)
                    img = images[0] if images else None
                else:
                    img = Image.open(image_input)
            elif isinstance(image_input, Image.Image):
                img = image_input
            else:
                return self._get_error_ticket(page_num, "Formato no válido")
            
            if not img:
                return self._get_error_ticket(page_num, "No se pudo cargar imagen")
            
            # Convertir imagen a bytes
            import io
            buffer = io.BytesIO()
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(buffer, format='JPEG', quality=95)
            buffer.seek(0)
            
            # Enviar a n8n webhook como multipart (archivo binario)
            files = {'image': ('ticket.jpg', buffer, 'image/jpeg')}
            data = {'page': str(page_num), 'format': 'binary'}
            
            logger.info(f"📤 Enviando imagen a n8n webhook: {webhook_url}")
            response = requests.post(webhook_url, files=files, data=data, timeout=180)
            
            if response.status_code != 200:
                logger.error(f"Error en n8n webhook: {response.status_code} - {response.text[:200]}")
                return self._get_error_ticket(page_num, f"Error n8n: {response.status_code}")
            
            result = response.json()
            logger.info(f"📥 Respuesta CRUDA de n8n: {json.dumps(result, default=str)[:600]}")
            logger.info(f"🔍 DEBUG tipo={type(result).__name__}, claves={list(result.keys()) if isinstance(result, dict) else 'N/A'}")
            if isinstance(result, dict):
                for k, v in result.items():
                    logger.info(f"  clave '{k}': tipo={type(v).__name__}, valor={json.dumps(v, default=str)[:200]}")
            elif isinstance(result, list):
                logger.info(f"  es lista de {len(result)} elementos")
            
            # Intentar extraer datos de la respuesta en varios formatos posibles
            data = None
            
            if isinstance(result, dict):
                # Caso 1: viene directamente con la estructura esperada
                if 'paciente' in result or 'totales' in result:
                    data = result
                # Caso 2: envuelto en 'json' o 'data' (formato común en nodos n8n)
                elif 'json' in result and isinstance(result['json'], dict):
                    data = result['json']
                elif 'data' in result and isinstance(result['data'], dict):
                    data = result['data']
                elif 'body' in result and isinstance(result['body'], dict):
                    data = result['body']
                # Caso 3: tiene campo 'text' con JSON string (salida de Gemini)
                elif 'text' in result and isinstance(result['text'], str):
                    try:
                        parsed = json.loads(result['text'])
                        data = parsed
                    except:
                        data = result
                else:
                    data = result  # usar lo que vino
            
            elif isinstance(result, str):
                try:
                    data = json.loads(result)
                except:
                    data = self._parse_n8n_text(result)
            
            elif isinstance(result, list) and len(result) > 0:
                data = result[0] if isinstance(result[0], dict) else None
            
            if data:
                # Normalizar paciente por si viene como array en vez de objeto
                if 'paciente' in data and isinstance(data['paciente'], list):
                    data['paciente'] = data['paciente'][0] if data['paciente'] else {}
                return data
            
            return self._get_error_ticket(page_num, "No se pudieron extraer datos de la respuesta")
                
        except Exception as e:
            logger.error(f"Error en n8n: {e}")
            return self._get_error_ticket(page_num, str(e))
    
    def _parse_n8n_text(self, text: str) -> Dict[str, Any]:
        """
        Parsea texto devuelto por n8n si no viene estructurado
        """
        logger.info("📊 Parseando texto de n8n...")
        
        result = {
            'paciente': {},
            'viaje': {},
            'totales': {},
            'pasaje': '',
            'fecha_ticket': '',
            'nro_doc': ''
        }
        
        text_upper = text.upper()
        text_lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        importe_patterns = [
            r'TOTAL[:\s]*\$?\s*(\d+[\.,]?\d*)',
            r'IMPORTE[:\s]*\$?\s*(\d+[\.,]?\d*)',
            r'MONTO[:\s]*\$?\s*(\d+[\.,]\d{2})',
            r'\$\s*(\d+[\.,]\d{2})',
            r'(\d{3,7}[\.,]\d{2})',
        ]
        
        for pattern in importe_patterns:
            match = re.search(pattern, text_upper)
            if match:
                try:
                    importe_str = match.group(1).replace('.', '').replace(',', '.').replace(' ', '')
                    importe = float(importe_str)
                    if importe > 0 and importe < 10000000:
                        result['totales']['importe_total'] = importe
                        break
                except:
                    pass
        
        for line in text_lines:
            skip = ['NOMBRE', 'CLIENTE', 'PASAJERO', 'TOTAL', 'IMPORTE', 'FECHA', 'TICKET']
            if any(w in line.upper() for w in skip):
                continue
            match = re.search(r'^([A-ZÁÉÍÓÚÑ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ]{2,}){1,2})', line)
            if match and 3 < len(line) < 45:
                result['paciente']['nombre'] = match.group(1).strip()
                break
        
        dni_patterns = [
            r'DNI[:\s]*(\d{6,9})',
            r'DNI\s+(\d{6,8})',
            r'(\d{2}\.\d{3}\.\d{3})',
            r'(\d{7,8})',
        ]
        for pattern in dni_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result['paciente']['dni'] = match.group(1).strip()
                result['nro_doc'] = match.group(1).strip()
                break
        
        fecha_patterns = [
            r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
            r'FECHA[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
        ]
        for pattern in fecha_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result['viaje']['fecha_viaje'] = match.group(0)
                result['fecha_ticket'] = match.group(0)
                break
        
        result['paciente']['encontrado'] = False
        result['paciente']['requiere_seleccion'] = True
        
        return result
    
    def _extract_with_ocr_local(self, image_input, page_num: int = 1) -> Dict[str, Any]:
        """
        Extrae datos usando OCR local (Tesseract + OpenCV)
        Se usa como respaldo cuando la IA no detecta importe ni paciente
        """
        logger.info(f"🔍 Usando OCR local para página {page_num}...")
        
        try:
            # Cargar imagen
            if isinstance(image_input, str):
                if image_input.lower().endswith('.pdf'):
                    from pdf2image import convert_from_path
                    images = convert_from_path(image_input, first_page=page_num, last_page=page_num)
                    img = images[0] if images else None
                else:
                    img = Image.open(image_input)
            elif isinstance(image_input, Image.Image):
                img = image_input
            else:
                return self._get_error_ticket(page_num, "Formato no válido para OCR")
            
            if not img:
                return self._get_error_ticket(page_num, "No se pudo cargar imagen")
            
            # Preprocesar imagen
            img_processed = self._preprocess_for_ocr(img)
            
            # Extraer texto
            if TESSERACT_AVAILABLE:
                custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:$/-() '
                text = pytesseract.image_to_string(img_processed, lang='spa+eng', config=custom_config)
            else:
                return self._get_error_ticket(page_num, "Tesseract no disponible")
            
            logger.info(f"📝 Texto OCR (primeros 500 chars): {text[:500]}")
            
            # Parsear datos del texto
            data = self._parse_ocr_text(text)
            
            # Normalizar datos
            data = self._normalize_ticket_data(data)
            
            logger.info(f"✅ Datos extraídos con OCR local: {data.get('totales', {}).get('importe_total')} | {data.get('paciente', {}).get('nombre')}")
            
            return data
            
        except Exception as e:
            logger.error(f"Error en OCR local: {e}")
            return self._get_error_ticket(page_num, f"Error OCR local: {str(e)}")
    
    def _preprocess_for_ocr(self, img: Image.Image) -> Image.Image:
        """
        Preprocesa la imagen para mejorar el reconocimiento de OCR
        """
        if not CV2_AVAILABLE:
            logger.warning("OpenCV no disponible, omitiendo preprocesamiento")
            return img
        
        logger.info("🔧 Preprocesando imagen para OCR...")
        
        # Convertir a numpy array
        img_array = np.array(img)
        
        # Convertir a escala de grises
        if len(img_array.shape) == 3:
            if img_array.shape[2] == 4:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2GRAY)
            else:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Reducir ruido
        img_array = cv2.GaussianBlur(img_array, (5, 5), 0)
        
        # Umbral adaptativo
        thresh = cv2.adaptiveThreshold(
            img_array, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Mejorar texto
        kernel = np.ones((1, 1), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        return Image.fromarray(thresh)
    
    def _parse_ocr_text(self, text: str) -> Dict[str, Any]:
        """
        Parsea el texto extraído por OCR para identificar campos del ticket
        """
        logger.info("📊 Parseando texto OCR...")
        
        result = {
            'paciente': {},
            'viaje': {},
            'totales': {},
            'pasaje': '',
            'fecha_ticket': '',
            'nro_doc': ''
        }
        
        text_upper = text.upper()
        text_lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Buscar importe (múltiples patrones)
        importe_patterns = [
            r'TOTAL[:\s]*\$?\s*(\d+[\.,]?\d*)',
            r'IMPORTE[:\s]*\$?\s*(\d+[\.,]?\d*)',
            r'MONTO[:\s]*\$?\s*(\d+[\.,]\d{2})',
            r'\$\s*(\d+[\.,]\d{2})',
            r'(\d{3,6}[\.,]\d{2})',
        ]
        
        for pattern in importe_patterns:
            match = re.search(pattern, text_upper)
            if match:
                try:
                    importe = match.group(1).replace('.', '').replace(',', '.')
                    result['totales']['importe_total'] = float(importe)
                    logger.info(f"💰 OCR detectó importe: ${importe}")
                    break
                except:
                    pass
        
        # Buscar nombre
        for line in text_lines:
            skip = ['NOMBRE', 'CLIENTE', 'PASAJERO', 'TOTAL', 'IMPORTE', 'FECHA', 'TICKET', 'BOLETO', 'PEAJE', 'DNI', 'DOC']
            if any(w in line.upper() for w in skip):
                continue
            match = re.search(r'^([A-ZÁÉÍÓÚÑ]{2,})\s+([A-ZÁÉÍÓÚÑ]{2,})', line)
            if match and 5 < len(line) < 40:
                result['paciente']['nombre'] = f"{match.group(1)} {match.group(2)}"
                break
        
        # Buscar DNI
        dni_patterns = [r'DNI[:\s]*(\d{6,9})', r'(\d{7,8})', r'(\d{2}\.\d{3}\.\d{3})']
        for pattern in dni_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result['paciente']['dni'] = match.group(1)
                result['nro_doc'] = match.group(1)
                break
        
        # Buscar fecha
        fecha_patterns = [r'(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})']
        for pattern in fecha_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result['viaje']['fecha_viaje'] = match.group(1)
                result['fecha_ticket'] = match.group(1)
                break
        
        # Buscar distancia
        dist_patterns = [r'(\d+[\.,]?\d*)\s*KM', r'DISTANCIA[:\s]*(\d+[\.,]?\d*)']
        for pattern in dist_patterns:
            match = re.search(pattern, text_upper)
            if match:
                try:
                    result['viaje']['distancia'] = float(match.group(1).replace(',', '.'))
                    result['viaje']['unidad'] = 'km'
                except:
                    pass
                break
        
        # Buscar pasaje/ticket
        pasaje_patterns = [r'PASAJE[:\s]*([A-Z0-9\-]+)', r'TICKET[:\s]*([A-Z0-9\-]+)']
        for pattern in pasaje_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result['pasaje'] = match.group(1)
                break
        
        # Por defecto marcar como no encontrado
        result['paciente']['encontrado'] = False
        result['paciente']['requiere_seleccion'] = True
        
        return result

    def _get_error_ticket(self, page_num: int, error_msg: str) -> Dict[str, Any]:
        """Retorna un ticket que representa un error de procesamiento"""
        return {
            '_error': True,
            '_error_message': error_msg,
            '_pagina': page_num,
            '_requiere_seleccion': True,
            '_insertar': False,
            'paciente': {
                'encontrado': False,
                'requiere_seleccion': True,
                'nombre': f'ERROR: {error_msg[:50]}',
                'dni': ''
            },
            'viaje': {},
            'totales': {}
        }
        
    def _registrar_error(self, error: Dict[str, Any]) -> None:
        """Registra el error en un archivo para debug y almacena el último error"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Guardar error detallado en archivo
        error_file = f"error_log_{timestamp}.txt"
        with open(error_file, 'w', encoding='utf-8') as f:
            f.write(f"=== ERROR REPORT ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Tipo: {error.get('tipo')}\n")
            f.write(f"Página: {error.get('pagina')}\n")
            f.write(f"Mensaje: {error.get('mensaje')}\n")
            if 'detalle' in error:
                f.write(f"Detalle: {error.get('detalle')}\n")
            if 'respuesta_cruda' in error:
                f.write(f"\n--- Respuesta cruda ---\n{error.get('respuesta_cruda')}\n")
            f.write(f"\n--- Traceback ---\n{error.get('traceback')}\n")

        # Almacenar el último error para enviarlo a la interfaz
        self._ultimo_error = error
        
    def _normalize_ticket_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza la estructura de datos del ticket"""

        normalized = self._get_empty_ticket()

        if not data or not isinstance(data, dict):
            logger.warning("Datos inválidos para normalizar")
            return normalized

        # Extraer pasaje
        if data.get("pasaje"):
            normalized["pasaje"] = str(data["pasaje"])

        # Extraer fecha_ticket
        if data.get("fecha_ticket"):
            normalized["fecha_ticket"] = data["fecha_ticket"]

        # 🔥 EXTRAER PACIENTE - SOPORTAR AMBOS FORMATOS
        nombre = None
        dni = None

        # Formato 1: {"paciente": {"nombre": "...", "dni": "..."}}
        if "paciente" in data:
            paciente_data = data["paciente"]
            if isinstance(paciente_data, dict):
                nombre = paciente_data.get("nombre")
                dni = paciente_data.get("dni")
            elif isinstance(paciente_data, list) and len(paciente_data) > 0:
                nombre = paciente_data[0].get("nombre")
                dni = paciente_data[0].get("dni")

        # Formato 2: {"nombre": "...", "dni": "..."} (directo de Gemini)
        if not nombre and data.get("nombre"):
            nombre = data.get("nombre")
        if not dni and data.get("dni"):
            dni = data.get("dni")

        if nombre:
            normalized["paciente"]["nombre"] = nombre
        if dni:
            normalized["paciente"]["dni"] = str(dni)

        # Extraer viaje
        viaje_data = data.get("viaje", {})
        if isinstance(viaje_data, dict):
            if viaje_data.get("fecha_viaje"):
                normalized["viaje"]["fecha_viaje"] = viaje_data["fecha_viaje"]
            if viaje_data.get("distancia"):
                normalized["viaje"]["distancia"] = viaje_data["distancia"]
            if viaje_data.get("unidad"):
                normalized["viaje"]["unidad"] = viaje_data["unidad"]
        elif isinstance(viaje_data, list) and len(viaje_data) > 0:
            if viaje_data[0].get("fecha_viaje"):
                normalized["viaje"]["fecha_viaje"] = viaje_data[0]["fecha_viaje"]
            if viaje_data[0].get("distancia"):
                normalized["viaje"]["distancia"] = viaje_data[0]["distancia"]
            if viaje_data[0].get("unidad"):
                normalized["viaje"]["unidad"] = viaje_data[0]["unidad"]

        # Extraer totales
        totales_data = data.get("totales", {})
        if isinstance(totales_data, dict):
            if totales_data.get("importe_total"):
                normalized["totales"]["importe_total"] = totales_data["importe_total"]
        elif isinstance(totales_data, list) and len(totales_data) > 0:
            if totales_data[0].get("importe_total"):
                normalized["totales"]["importe_total"] = totales_data[0]["importe_total"]

        logger.info(f"Datos normalizados: paciente='{normalized['paciente']['nombre']}', DNI='{normalized['paciente']['dni']}', importe={normalized['totales']['importe_total']}")

        return normalized

    def _get_empty_ticket(self) -> Dict[str, Any]:
        """Retorna un ticket vacío con toda la estructura necesaria"""
        return {
            "pasaje": "",
            "fecha_ticket": "",
            "paciente": {"nombre": "", "dni": ""},
            "viaje": {"fecha_viaje": "", "distancia": None, "unidad": ""},
            "totales": {"subtotal": None, "importe_total": None}
        }
    
    def extract_tickets_from_pdf(self, pdf_path: str, validate: bool = True) -> List[Dict[str, Any]]:
        """Extrae múltiples tickets de un PDF"""
        
        try:
            images = pdf2image.convert_from_path(pdf_path)
            logger.info(f"PDF tiene {len(images)} páginas")
        except Exception as e:
            logger.error(f"Error convirtiendo PDF: {e}")
            return []
        
        all_tickets = []
        
        for page_num, img in enumerate(images, start=1):
            logger.info(f"Procesando página {page_num} de {len(images)}")
            ticket_data = self.extract_from_image(img, page_num, validate=validate)
            
            # 🔥 Siempre agregar (puede ser None, pero extract_from_image nunca retorna None ahora)
            if ticket_data:
                all_tickets.append(ticket_data)
            else:
                logger.warning(f"Página {page_num}: No se pudo extraer ticket")
        
        logger.info(f"Total de tickets extraídos: {len(all_tickets)} de {len(images)} páginas")
        return all_tickets

    def generate_insert_sql(self, data: Dict[str, Any], usuario: str = None) -> str:
        """Genera sentencia INSERT - solo se llama si paciente fue encontrado"""

        paciente = data.get('paciente', {})
        viaje = data.get('viaje', {})
        totales = data.get('totales', {})

        # Usar el nombre ya corregido (concatenado de BD)
        nombre = paciente.get('nombre', '')
        id_paciente = paciente.get('persona_id')
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
                protocolo, importe_total, pasaje, create_time, usuario, id_paciente
            ) VALUES (
                :paciente, :fecha_viaje, :fecha_ticket, :distancia, :unidad,
                :protocolo, :importe_total, :pasaje, NOW(), :usuario, :id_paciente
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
            'usuario': usuario_registro[:100] if usuario_registro else None,
            'id_paciente': id_paciente
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
            'tickets_pendientes': [],  
            'tickets_automaticos': [],
            'tickets_con_error': [],
            'errores': [],
            'tickets': [],
            'archivo_movido': False,
            'message': ''
        }

        try:
            # Extraer datos
            if file_path.lower().endswith('.pdf'):
                tickets_data = self.extract_tickets_from_pdf(file_path, validate=validate)
            else:
                ticket_data = self.extract_from_image(file_path, validate=validate)
                tickets_data = [ticket_data] if ticket_data else []

                    # 🔥 CAPTURAR ERRORES DE EXTRACCIÓN
            for td in tickets_data:
                if td and '_error' in td:
                    result['errores'].append(td['_error'])

            # Filtrar tickets válidos (sin error)
            valid_tickets = [td for td in tickets_data if td and '_error' not in td]
            result['tickets_procesados'] = len(valid_tickets)

            if len(tickets_data) > 0 and len(valid_tickets) == 0:
                # Todos los tickets tienen error
                result['message'] = f"Error en extracción: {len(result['errores'])} error(es)"
                result['success'] = False
                return result
            logger.info(f"Tickets extraídos: {len(tickets_data)}")

            # Procesar cada ticket
            for idx, ticket_data in enumerate(tickets_data, start=1):
                # =====================================================
                # 📋 LOG DETALLADO DE CADA TICKET PROCESADO
                # =====================================================
                logger.info("-" * 60)
                logger.info(f"🎫 PROCESANDO TICKET {idx}/{len(tickets_data)}")
                logger.info("-" * 60)
                
                # Mostrar datos del paciente
                paciente = ticket_data.get('paciente', {})
                logger.info(f"👤 Paciente: {paciente.get('nombre', 'N/A')} {paciente.get('apellido', '')}")
                logger.info(f"   DNI: {paciente.get('dni', 'N/A')} | Protocolo: {paciente.get('protocolo', 'N/A')}")
                
                # Mostrar datos del viaje
                viaje = ticket_data.get('viaje', {})
                logger.info(f"🚗 Viaje: {viaje.get('distancia', 'N/A')} {viaje.get('unidad', '')} - {viaje.get('fecha_viaje', 'N/A')}")
                
                # Mostrar totales
                totales = ticket_data.get('totales', {})
                logger.info(f"💰 Importe: ${totales.get('importe_total', 'N/A')} | Pasaje: ${totales.get('importe_pasaje', 'N/A')}")
                
                # Mostrar pasaje y fecha
                logger.info(f"🎫 Pasaje: {ticket_data.get('pasaje', 'N/A')}")
                logger.info(f"📅 Fecha ticket: {ticket_data.get('fecha_ticket', 'N/A')}")
                
                # 🔥 Verificar si es un ticket con error
                if ticket_data.get('_error'):
                    result['tickets_con_error'].append({
                        'index': idx,
                        'error': ticket_data.get('_error_message', 'Error desconocido'),
                        'pagina': ticket_data.get('_pagina', idx)
                    })
                    logger.error(f"❌ Ticket {idx} tiene error: {ticket_data.get('_error_message')}")
                    continue

                # Verificar si se puede insertar automáticamente
                insertar_auto = ticket_data.get('_insertar', False)

                if insertar_auto:
                    # ✅ Inserción automática
                    sql_query = self.generate_insert_sql(ticket_data, usuario)
                    insert_result = self.insert_ticket(sql_query, file_path)

                    if insert_result['success']:
                        result['tickets_insertados'] += 1
                        result['tickets_automaticos'].append({
                            'index': idx,
                            'ticket_id': insert_result.get('ticket_id'),
                            'nombre': ticket_data.get('paciente', {}).get('nombre', '')
                        })
                        logger.info(f"✅ Ticket {idx} insertado automáticamente")
                    else:
                        result['errores'].append({
                            'ticket': idx,
                            'error': insert_result.get('message')
                        })
                else:
                    # ⏳ Requiere selección manual
                    result['tickets_pendientes'].append({
                        'index': idx,
                        'nombre': ticket_data.get('paciente', {}).get('nombre', ''),
                        'dni': ticket_data.get('paciente', {}).get('dni', ''),
                        'candidatos': ticket_data.get('paciente', {}).get('candidatos', []),
                        'extracted_data': ticket_data
                    })
                    logger.warning(f"⚠️ Ticket {idx} pendiente de selección manual")

            result['success'] = True  # Siempre true porque procesamos todos
            result['message'] = f"Procesados {result['tickets_procesados']} tickets: {result['tickets_insertados']} insertados automáticamente, {len(result['tickets_pendientes'])} pendientes de selección"

            # No mover archivo si hay pendientes (para poder reprocesar)
            if move_to_processed and result['tickets_insertados'] > 0 and len(result['tickets_pendientes']) == 0:
                processed_path = self.move_to_processed(file_path)
                result['processed_path'] = processed_path
                result['archivo_movido'] = True
                
            if result['tickets_con_error']:
                result['message'] = f"Procesados: {result['tickets_insertados']} insertados, {len(result['tickets_con_error'])} con error de API, {len(result['tickets_pendientes'])} pendientes"
                result['success'] = False
            else:
                result['message'] = f"Procesados: {result['tickets_insertados']} insertados, {len(result['tickets_pendientes'])} pendientes"
                result['success'] = True

            return result

        
        except Exception as e:
            import traceback
            error_detalle = {
                'tipo': type(e).__name__,
                'mensaje': str(e),
                'traceback': traceback.format_exc(),
                'fase': 'procesamiento_archivo'
            }
            result['errores'].append(error_detalle)
            result['message'] = f'Error en procesamiento: {str(e)}'
            result['success'] = False
            logger.exception("Error procesando archivo")

            # No mover archivo si hubo error
            if os.path.exists(file_path) and move_to_processed:
                logger.info(f"Archivo {file_path} permanece en uploads para reintentar")

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
        """Procesa un archivo subido - SIEMPRE retorna un diccionario"""

        # Resultado por defecto (en caso de error)
        default_result = {
            'success': False,
            'file_path': file_path,
            'usuario': usuario,
            'tickets_procesados': 0,
            'tickets_insertados': 0,
            'tickets_omitidos': 0,
            'errores': [],
            'tickets': [],
            'archivo_movido': False,
            'message': 'Error desconocido en el procesador'
        }

        if not self.processor:
            default_result['message'] = 'Procesador no inicializado'
            default_result['errores'].append({'error': 'Procesador no inicializado'})
            return default_result

        try:
            result = self.processor.process_multiple_tickets(
                file_path, usuario, move_to_processed, validate_protocolo
            )

            # Asegurar que el resultado es un diccionario
            if result is None:
                return default_result

            return result

        except Exception as e:
            import traceback
            default_result['message'] = f'Error en procesamiento: {str(e)}'
            default_result['errores'].append({
                'tipo': type(e).__name__,
                'mensaje': str(e),
                'traceback': traceback.format_exc()
            })
            return default_result
    
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