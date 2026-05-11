import os
import json
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class PromptManager:
    """Gestiona la carga y gestión de prompts desde archivos"""
    
    def __init__(self, prompts_folder: str = "prompts"):
        """
        Inicializa el gestor de prompts
        
        Args:
            prompts_folder: Carpeta donde están los archivos de prompts
        """
        self.prompts_folder = Path(prompts_folder)
        self.prompts_folder.mkdir(exist_ok=True)
        self._cache = {}
        self.config = self._load_config()
        
    def _load_config(self) -> Dict:
        """Carga la configuración desde config.json"""
        config_path = self.prompts_folder / "config.json"
        
        if not config_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de configuración: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"Configuración cargada desde {config_path}")
                return config
        except json.JSONDecodeError as e:
            raise ValueError(f"Error en formato JSON del archivo {config_path}: {e}")
        except Exception as e:
            raise Exception(f"Error leyendo archivo {config_path}: {e}")
    
    def _save_config(self, config: Dict):
        """Guarda la configuración"""
        config_path = self.prompts_folder / "config.json"
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info(f"Configuración guardada en {config_path}")
        except Exception as e:
            logger.error(f"Error guardando config: {e}")
    
    def load_prompt(self, prompt_name: str) -> str:
        """
        Carga un prompt desde archivo
        
        Args:
            prompt_name: Nombre del archivo (ej: "extract_ticket.txt")
            
        Returns:
            Contenido del prompt
        """
        # Verificar caché
        if prompt_name in self._cache:
            return self._cache[prompt_name]
        
        prompt_path = self.prompts_folder / prompt_name
        
        if not prompt_path.exists():
            # Crear prompt por defecto
            default_prompt = self._get_default_prompt(prompt_name)
            self._save_prompt(prompt_name, default_prompt)
            return default_prompt
        
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self._cache[prompt_name] = content
                return content
        except Exception as e:
            logger.error(f"Error cargando prompt {prompt_name}: {e}")
            return self._get_default_prompt(prompt_name)
    
    def _save_prompt(self, prompt_name: str, content: str):
        """Guarda un prompt en archivo"""
        prompt_path = self.prompts_folder / prompt_name
        try:
            with open(prompt_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Prompt guardado en {prompt_path}")
        except Exception as e:
            logger.error(f"Error guardando prompt {prompt_name}: {e}")
    
    def _get_default_prompt(self, prompt_name: str) -> str:
        """Retorna prompt por defecto si el archivo no existe"""
        defaults = {
            "extract_ticket.txt": """Extrae los siguientes datos del ticket médico en formato JSON:
- pasaje: número de pasaje/comprobante
- fecha_ticket: fecha del ticket
- paciente: {nombre, dni, protocolo}
- viaje: {fecha_viaje, distancia, unidad}
- totales: {subtotal, iva, otros_tributos, importe_total}

Devuelve SOLO el JSON, sin texto adicional.""",
            
            "extract_ticket_multi.txt": """Extrae TODOS los tickets visibles en la imagen. 
Para cada ticket, extrae:
- pasaje, fecha_ticket, paciente, viaje, totales

Devuelve un JSON con estructura: {"tickets": [...]}"""
        }
        
        return defaults.get(prompt_name, f"Prompt no definido: {prompt_name}")
    
    def reload_prompt(self, prompt_name: str):
        """Recarga un prompt desde archivo (elimina caché)"""
        if prompt_name in self._cache:
            del self._cache[prompt_name]
        return self.load_prompt(prompt_name)
    
    def get_single_ticket_prompt(self) -> str:
        """Obtiene el prompt para extracción de ticket único"""
        prompt_file = self.config['extraction']['single_ticket_prompt']
        return self.load_prompt(prompt_file)
    
    def get_multi_ticket_prompt(self) -> str:
        """Obtiene el prompt para extracción de múltiples tickets"""
        prompt_file = self.config['extraction']['multi_ticket_prompt']
        return self.load_prompt(prompt_file)
    
    def get_model_config(self) -> Dict:
        """Obtiene la configuración del modelo"""
        return {
            'model': self.config.get('model', 'gemma-3-4b-it'),
            'temperature': self.config.get('temperature', 0.1),
            'max_output_tokens': self.config.get('max_output_tokens', 2048)
        }