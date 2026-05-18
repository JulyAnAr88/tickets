"""
OCR Processor - Extracción de datos de tickets con Tesseract + Preprocesamiento
Alternativa local a Gemini para el escaneo de tickets
"""

import os
import re
import json
import logging
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)

# Intentar importar librerías opcionales
try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow no disponible, funcionalidades limitadas")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV no disponible")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("Tesseract no disponible, usando método alternativo")


class OCRProcessor:
    """
    Procesador de OCR para tickets de peaje/cabina
    Utiliza Tesseract con preprocesamiento de imágenes para mejor precisión
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.language = self.config.get('language', 'spa+eng')
        
        # Configurar Tesseract si está disponible
        if TESSERACT_AVAILABLE:
            tesseract_cmd = self.config.get('tesseract_cmd', None)
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    
    def process_image(self, image_path: str) -> Dict[str, Any]:
        """
        Procesa una imagen de ticket y extrae los datos
        
        Args:
            image_path: Ruta de la imagen o PDF convertido
            
        Returns:
            Diccionario con los datos extraídos del ticket
        """
        logger.info(f"🖼️ Procesando imagen: {image_path}")
        
        if not PIL_AVAILABLE:
            logger.error("Pillow no disponible")
            return self._get_error_ticket("Pillow no disponible")
        
        try:
            # Cargar imagen
            img = Image.open(image_path)
            logger.info(f"📐 Imagen cargada: {img.size}, modo: {img.mode}")
            
            # Preprocesar imagen
            processed_img = self._preprocess_image(img)
            
            # Extraer texto con OCR
            if TESSERACT_AVAILABLE:
                text = self._extract_text_tesseract(processed_img)
            else:
                text = self._extract_text_fallback(processed_img)
            
            logger.info(f"📝 Texto extraído (primeros 500 chars): {text[:500]}")
            
            # Parsear datos del texto
            ticket_data = self._parse_ticket_text(text)
            
            # Agregar metadatos
            ticket_data['_ocr_method'] = 'tesseract' if TESSERACT_AVAILABLE else 'fallback'
            ticket_data['_raw_text'] = text
            
            logger.info(f"✅ Datos extraídos: {ticket_data.get('paciente', {})} | {ticket_data.get('totales', {})}")
            
            return ticket_data
            
        except Exception as e:
            logger.exception(f"Error procesando imagen: {e}")
            return self._get_error_ticket(str(e))
    
    def process_pdf_page(self, pdf_path: str, page_num: int = 1) -> Dict[str, Any]:
        """Procesa una página específica de un PDF"""
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(pdf_path, first_page=page_num, last_page=page_num)
            if images:
                # Guardar imagen temporalmente
                temp_path = f"/tmp/temp_page_{page_num}.jpg"
                images[0].save(temp_path, 'JPEG')
                
                # Procesar
                result = self.process_image(temp_path)
                
                # Limpiar
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                return result
            return self._get_error_ticket("No se pudieron extraer imágenes del PDF")
        except Exception as e:
            logger.exception(f"Error procesando PDF página {page_num}: {e}")
            return self._get_error_ticket(str(e))
    
    def _preprocess_image(self, img: Image.Image) -> Image.Image:
        """
        Preprocesa la imagen para mejorar el reconocimiento de OCR
        Usa OpenCV para mejor calidad de preprocesamiento
        """
        logger.info("🔧 Preprocesando imagen...")
        
        # Convertir imagen PIL a numpy array para OpenCV
        img_array = np.array(img)
        
        # Convertir a escala de grises si es necesario
        if len(img_array.shape) == 3:
            if img_array.shape[2] == 4:  # RGBA
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2GRAY)
            else:  # RGB
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Aplicar desenfoque gaussiano para reducir ruido
        img_array = cv2.GaussianBlur(img_array, (5, 5), 0)
        
        # Aplicar umbral adaptativo (mejor que fijo para tickets)
        thresh = cv2.adaptiveThreshold(
            img_array, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Invertir si el fondo es claro y el texto oscuro
        # (algunas imágenes tienen fondo blanco con texto negro)
        
        # Aplicar morfología para mejorar texto
        kernel = np.ones((1, 1), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        
        # Convertir de vuelta a PIL
        result_img = Image.fromarray(thresh)
        
        logger.info("✅ Preprocesamiento completado (OpenCV)")
        return result_img
    
    def _extract_text_tesseract(self, img: Image.Image) -> str:
        """Extrae texto usando Tesseract OCR"""
        logger.info("🔍 Extrayendo texto con Tesseract...")
        
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:$/-() '
        
        text = pytesseract.image_to_string(
            img,
            lang=self.language,
            config=custom_config
        )
        
        return text
    
    def _extract_text_fallback(self, img: Image.Image) -> str:
        """
        Método alternativo cuando Tesseract no está disponible
        Usa análisis de luminosidad para detectar texto (menos preciso)
        """
        logger.warning("⚠️ Usando método alternativo (sin Tesseract)")
        
        # Este método es muy básico y limitado
        # Solo devuelve algo de texto si se configuró algo más
        
        # Intentar usar Pillow para obtener datos de resolución
        width, height = img.size
        
        # Crear una estimación básica (muy limitada)
        text = f"[Imagen procesada: {width}x{height} píxeles - Sin OCR disponible]"
        
        return text
    
    def _parse_ticket_text(self, text: str) -> Dict[str, Any]:
        """
        Parsea el texto extraído para identificar los campos del ticket
        Mejorado para detectar más campos
        """
        logger.info("📊 Parseando texto del ticket...")
        
        result = {
            'paciente': {},
            'viaje': {},
            'totales': {},
            'pasaje': '',
            'fecha_ticket': '',
            'nro_doc': ''
        }
        
        # Normalizar texto
        text_upper = text.upper()
        text_lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # ==================== BUSCAR NOMBRE ====================
        # Buscar en líneas completas que parezcan nombres
        for line in text_lines:
            # Ignorar líneas que parecen ser encabezados o valores conocida
            skip_words = ['NOMBRE', 'CLIENTE', 'PASAJERO', 'BENEFICIARIO', 'TOTAL', 'IMPORTE', 'FECHA', 'HORA', 'DISTANCIA', 'TICKET', 'BOLETO', 'PEAJE', 'CABINA']
            if any(word in line.upper() for word in skip_words):
                continue
            
            # Buscar patrones de nombre (dos palabras que empiezan con mayúscula)
            match = re.search(r'^([A-ZÁÉÍÓÚÑ]{2,})\s+([A-ZÁÉÍÓÚÑ]{2,})(?:\s+[A-ZÁÉÍÓÚÑ]+)?$', line)
            if match and len(line) < 40:  # Nombres no muy largos
                nombre = f"{match.group(1)} {match.group(2)}"
                # Filtrar palabras que no son nombres
                if nombre and len(nombre) > 3:
                    result['paciente']['nombre'] = nombre
                    break
        
        # ==================== BUSCAR DNI ====================
        # Patrones para DNI (varios formatos)
        dni_patterns = [
            r'DNI[:\s]*(\d{6,9})',
            r'DOC\.?[:\s]*(\d{6,9})',
            r'(\d{2}\.\d{3}\.\d{3})',
            r'(\d{8})',
            r'(\d{7})',
            r'NRO[\.\s]*(\d{6,8})',
        ]
        
        for pattern in dni_patterns:
            match = re.search(pattern, text_upper)
            if match:
                dni = match.group(1).strip()
                result['paciente']['dni'] = dni
                result['nro_doc'] = dni
                break
        
        # ==================== BUSCAR PROTOCOLO ====================
        protocolo_patterns = [
            r'PROTOCOLO[:\s]*(\d+)',
            r'PROT[\.\s]*(\d+)',
            r'REFERENCIA[:\s]*(\d+)',
            r'REF[\.\s]*(\d+)',
            r'TICKET\s*(?:NRO|NÚMERO)?[:\s]*(\d+)',
        ]
        
        for pattern in protocolo_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result['paciente']['protocolo'] = match.group(1).strip()
                break
        
        # ==================== BUSCAR FECHA ====================
        fecha_patterns = [
            r'(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})',
            r'(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})',
            r'FECHA[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
            r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\s+(\d{1,2}):(\d{2})',
        ]
        
        for pattern in fecha_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result['viaje']['fecha_viaje'] = match.group(0)
                result['fecha_ticket'] = match.group(0)
                break
        
        # ==================== BUSCAR DISTANCIA ====================
        distancia_patterns = [
            r'(\d+[\.,]?\d*)\s*(?:KM|KILÓMETROS|KILOMETROS)',
            r'DISTANCIA[:\s]*(\d+[\.,]?\d*)',
            r'KM[:\s]*(\d+[\.,]?\d*)',
        ]
        
        for pattern in distancia_patterns:
            match = re.search(pattern, text_upper)
            if match:
                try:
                    distancia = match.group(1).replace(',', '.')
                    result['viaje']['distancia'] = float(distancia)
                    result['viaje']['unidad'] = 'km'
                except:
                    pass
                break
        
        # ==================== BUSCAR IMPORTES ====================
        # Importe total
        importe_total_patterns = [
            r'TOTAL[:\s]*\$?\s*(\d+[\.,]?\d*)',
            r'IMPORTE[:\s]*\$?\s*(\d+[\.,]?\d*)',
            r'MONTO[:\s]*\$?\s*(\d+[\.,]?\d*)',
            r'\$\s*(\d+[\.,]\d{2})',
        ]
        
        for pattern in importe_total_patterns:
            match = re.search(pattern, text_upper)
            if match:
                try:
                    importe = match.group(1).replace('.', '').replace(',', '.')
                    result['totales']['importe_total'] = float(importe)
                except:
                    pass
                break
        
        # Importe pasaje
        pasaje_patterns = [
            r'PASAJE[:\s]*\$?\s*(\d+[\.,]?\d*)',
            r'TARIFA[:\s]*\$?\s*(\d+[\.,]?\d*)',
        ]
        
        for pattern in pasaje_patterns:
            match = re.search(pattern, text_upper)
            if match:
                try:
                    importe = match.group(1).replace('.', '').replace(',', '.')
                    result['totales']['importe_pasaje'] = float(importe)
                except:
                    pass
                break
        
        # Importe peaje
        peaje_patterns = [
            r'PEAJE[:\s]*\$?\s*(\d+[\.,]?\d*)',
        ]
        
        for pattern in peaje_patterns:
            match = re.search(pattern, text_upper)
            if match:
                try:
                    importe = match.group(1).replace('.', '').replace(',', '.')
                    result['totales']['importe_peaje'] = float(importe)
                except:
                    pass
                break
        
        # ==================== BUSCAR PASAJE ====================
        pasaje_num_patterns = [
            r'PASAJE[:\s]*([A-Z0-9\-]+)',
            r'BOLETO[:\s]*([A-Z0-9\-]+)',
            r'FOLIO[:\s]*([A-Z0-9\-]+)',
            r'TICKET[:\s]*([A-Z0-9\-]+)',
        ]
        
        for pattern in pasaje_num_patterns:
            match = re.search(pattern, text_upper)
            if match:
                result['pasaje'] = match.group(1).strip()
                break
        
        # ==================== BUSCAR ORIGEN/DESTINO ====================
        # Buscar en líneas completas
        for i, line in enumerate(text_lines):
            if 'ORIGEN' in line.upper() or 'DESDE' in line.upper():
                if i + 1 < len(text_lines):
                    result['viaje']['desde'] = text_lines[i + 1].strip()
            if 'DESTINO' in line.upper() or 'HASTA' in line.upper():
                if i + 1 < len(text_lines):
                    result['viaje']['hasta'] = text_lines[i + 1].strip()
        
        # Por defecto, marcar como no encontrado (requiere validación)
        result['paciente']['encontrado'] = False
        result['paciente']['requiere_seleccion'] = True
        
        # Si no se encontró nombre pero hay DNI, usar el DNI como identificador
        if not result['paciente'].get('nombre') and result['paciente'].get('dni'):
            result['paciente']['nombre'] = f"DNI: {result['paciente']['dni']}"
        
        logger.info(f"📋 Datos parseados: {result}")
        return result
    
    def _get_error_ticket(self, error_msg: str) -> Dict[str, Any]:
        """Retorna un ticket de error"""
        return {
            '_error': True,
            '_error_message': error_msg,
            'paciente': {'nombre': '', 'dni': '', 'encontrado': False},
            'viaje': {},
            'totales': {},
            'pasaje': '',
            'fecha_ticket': ''
        }
    
    def extract_fields_from_coordinates(self, img: Image.Image, regions: Dict[str, Tuple]) -> Dict[str, str]:
        """
        Extrae texto de regiones específicas de la imagen
        Útil para tickets con formato fijo
        
        Args:
            img: Imagen preprocesada
            regions: Diccionario con nombre de campo y coordenadas (x1, y1, x2, y2)
            
        Returns:
            Diccionario con los campos extraídos
        """
        results = {}
        
        for field_name, coords in regions.items():
            try:
                # Recortar región
                cropped = img.crop(coords)
                
                # Extraer texto
                if TESSERACT_AVAILABLE:
                    text = pytesseract.image_to_string(cropped, lang=self.language)
                else:
                    text = ""
                
                results[field_name] = text.strip()
                
            except Exception as e:
                logger.warning(f"Error extrayendo {field_name}: {e}")
                results[field_name] = ""
        
        return results


# Instancia global del procesador
ocr_processor = None

def get_ocr_processor(config: Dict[str, Any] = None) -> OCRProcessor:
    """Obtiene la instancia global del procesador OCR"""
    global ocr_processor
    if ocr_processor is None:
        ocr_processor = OCRProcessor(config)
    return ocr_processor


def process_ticket_with_ocr(image_path: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Función de conveniencia para procesar un ticket con OCR
    
    Args:
        image_path: Ruta de la imagen del ticket
        config: Configuración opcional
        
    Returns:
        Diccionario con los datos extraídos del ticket
    """
    processor = get_ocr_processor(config)
    return processor.process_image(image_path)


if __name__ == '__main__':
    # Test básico
    logging.basicConfig(level=logging.INFO)
    processor = OCRProcessor()
    print(f"Tesseract disponible: {TESSERACT_AVAILABLE}")
    print(f"OpenCV disponible: {CV2_AVAILABLE}")
    print(f"Pillow disponible: {PIL_AVAILABLE}")