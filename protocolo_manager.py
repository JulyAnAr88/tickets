import sqlalchemy as sa
from sqlalchemy import text
from typing import Any, List, Dict, Optional, Tuple
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class ProtocoloManager:
    """Gestiona la búsqueda y actualización de protocolos y pacientes"""
    
    def __init__(self, engine):
        """
        Inicializa el gestor
        
        Args:
            engine: SQLAlchemy engine para conexión a BD
        """
        self.engine = engine
    
    # ============ MÉTODOS PARA PROTOCOLOS ============
    
    def get_all_protocolos(self) -> List[str]:
        """Obtiene todos los protocolos disponibles"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(
                    "SELECT identificador_protocolo FROM cedir.protocolo ORDER BY identificador_protocolo"
                ))
                return [row[0] for row in result.fetchall() if row[0]]
        except Exception as e:
            logger.error(f"Error obteniendo protocolos: {e}")
            return []
    
    def find_protocolo(self, texto: str, threshold: float = 0.7) -> Optional[str]:
        """Busca un protocolo por coincidencia de texto"""
        if not texto:
            return None
        
        protocolos = self.get_all_protocolos()
        
        # Búsqueda exacta (case insensitive)
        texto_lower = texto.strip().lower()
        for protocolo in protocolos:
            if protocolo and protocolo.lower() == texto_lower:
                logger.info(f"Protocolo encontrado exacto: '{texto}' -> '{protocolo}'")
                return protocolo
        
        # Búsqueda por similitud
        best_match = None
        best_ratio = 0
        
        for protocolo in protocolos:
            if not protocolo:
                continue
            ratio = SequenceMatcher(None, texto_lower, protocolo.lower()).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = protocolo
        
        if best_match:
            logger.info(f"Protocolo encontrado por similitud: '{texto}' -> '{best_match}' (ratio: {best_ratio})")
        else:
            logger.warning(f"Protocolo no encontrado: '{texto}'")
        
        return best_match
    
    # ============ MÉTODOS PARA PACIENTES ============
    
    def get_all_pacientes(self) -> List[Dict[str, str]]:
        """
        Obtiene todos los pacientes disponibles
        
        Returns:
            Lista de diccionarios con 'nombre_completo', 'nombre', 'apellido'
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        p.id,
                        p.nombre, 
                        p.apellido,
                        CONCAT(p.nombre, ' ', p.apellido) as nombre_completo
                    FROM cedir.persona p
                    INNER JOIN cedir.paciente p2 ON p2.id_persona = p.id
                    ORDER BY p.apellido, p.nombre
                """))
                return [
                    {
                        'id': row[0],
                        'nombre': row[1],
                        'apellido': row[2],
                        'nombre_completo': row[3]
                    }
                    for row in result.fetchall()
                ]
        except Exception as e:
            logger.error(f"Error obteniendo pacientes: {e}")
            return []
    
    def find_paciente(self, nombre: str, apellido: str = None, threshold: float = 0.7) -> Optional[Dict[str, str]]:
        """
        Busca un paciente por nombre y/o apellido
        
        Args:
            nombre: Nombre del paciente
            apellido: Apellido del paciente (opcional)
            threshold: Umbral de similitud
            
        Returns:
            Diccionario con datos del paciente o None
        """
        if not nombre:
            return None
        
        pacientes = self.get_all_pacientes()
        nombre_busqueda = nombre.strip().lower()
        apellido_busqueda = apellido.strip().lower() if apellido else None
        
        # Búsqueda exacta
        for paciente in pacientes:
            nombre_completo = paciente['nombre_completo'].lower()
            solo_nombre = paciente['nombre'].lower()
            solo_apellido = paciente['apellido'].lower()
            
            # Coincidencia exacta de nombre completo
            if nombre_busqueda == nombre_completo:
                logger.info(f"Paciente encontrado exacto: '{nombre}' -> {paciente['nombre_completo']}")
                return paciente
            
            # Coincidencia exacta solo por nombre
            if nombre_busqueda == solo_nombre:
                logger.info(f"Paciente encontrado por nombre: '{nombre}' -> {paciente['nombre_completo']}")
                return paciente
            
            # Si tenemos apellido, buscar coincidencia exacta
            if apellido_busqueda and apellido_busqueda == solo_apellido:
                logger.info(f"Paciente encontrado por apellido: '{apellido}' -> {paciente['nombre_completo']}")
                return paciente
        
        # Búsqueda por similitud
        best_match = None
        best_ratio = 0
        
        for paciente in pacientes:
            # Comparar con nombre completo
            ratio = SequenceMatcher(None, nombre_busqueda, paciente['nombre_completo'].lower()).ratio()
            
            # También comparar solo nombre
            ratio_nombre = SequenceMatcher(None, nombre_busqueda, paciente['nombre'].lower()).ratio()
            ratio = max(ratio, ratio_nombre)
            
            # Si tenemos apellido, comparar
            if apellido_busqueda:
                ratio_apellido = SequenceMatcher(None, apellido_busqueda, paciente['apellido'].lower()).ratio()
                ratio = max(ratio, ratio_apellido)
            
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = paciente
        
        if best_match:
            logger.info(f"Paciente encontrado por similitud: '{nombre}' -> {best_match['nombre_completo']} (ratio: {best_ratio})")
        else:
            logger.warning(f"Paciente no encontrado: '{nombre}'")
        
        return best_match
    
    def get_paciente_suggestions(self, partial: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Obtiene sugerencias de pacientes para autocompletar
        
        Args:
            partial: Texto parcial del nombre
            limit: Cantidad máxima de resultados
            
        Returns:
            Lista de pacientes sugeridos
        """
        if not partial or len(partial) < 2:
            return []
        
        pacientes = self.get_all_pacientes()
        partial_lower = partial.lower()
        
        matches = []
        for p in pacientes:
            if (partial_lower in p['nombre'].lower() or 
                partial_lower in p['apellido'].lower() or 
                partial_lower in p['nombre_completo'].lower()):
                matches.append(p)
        
        return matches[:limit]
    
    def buscar_paciente_protocolo(self, nombre_busqueda: str) -> Dict[str, Any]:
        """
        Busca un paciente por nombre (búsqueda flexible) y obtiene su protocolo

        Args:
            nombre_busqueda: Nombre o texto a buscar (ej: "farias", "esica farias")

        Returns:
            Diccionario con datos del paciente y protocolo, o None si no se encuentra
        """
        if not nombre_busqueda:
            return None

        try:
            with self.engine.connect() as conn:
                # Limpiar el nombre de búsqueda
                nombre_limpio = nombre_busqueda.strip().lower()

                # Dividir en posible nombre y apellido
                partes = nombre_limpio.split()
                nombre = partes[0] if partes else ''
                apellido = ' '.join(partes[1:]) if len(partes) > 1 else ''

                # Búsqueda por nombre o apellido
                query = """
                    SELECT 
                        p.nombre, 
                        p.apellido, 
                        pr.identificador_protocolo,
                        pr.id as protocolo_id,
                        p.id as persona_id
                    FROM cedir.persona p 
                    INNER JOIN cedir.paciente p2 ON p2.id_persona = p.id 
                    INNER JOIN cedir.paciente_protocolo pp ON pp.id_paciente = p2.id 
                    INNER JOIN cedir.protocolo pr ON pr.id = pp.id_protocolo
                    WHERE LOWER(p.nombre) = :nombre 
                       OR LOWER(p.apellido) = :apellido
                       OR LOWER(p.nombre) = :nombre_completo
                       OR LOWER(CONCAT(p.nombre, ' ', p.apellido)) LIKE :nombre_parcial
                       OR LOWER(CONCAT(p.apellido, ' ', p.nombre)) LIKE :nombre_parcial
                """

                params = {
                    'nombre': nombre,
                    'apellido': apellido if apellido else nombre,
                    'nombre_completo': nombre_limpio,
                    'nombre_parcial': f'%{nombre_limpio}%'
                }

                result = conn.execute(text(query), params)
                row = result.fetchone()

                if row:
                    logger.info(f"✅ Paciente encontrado: {row[0]} {row[1]} -> Protocolo: {row[2]}")
                    return {
                        'nombre': row[0],
                        'apellido': row[1],
                        'protocolo': row[2],
                        'protocolo_id': row[3],
                        'persona_id': row[4],
                        'nombre_completo': f"{row[0]} {row[1]}"
                    }

                # Búsqueda más flexible con LIKE
                query_like = """
                    SELECT 
                        p.nombre, 
                        p.apellido, 
                        pr.identificador_protocolo,
                        pr.id as protocolo_id,
                        p.id as persona_id
                    FROM cedir.persona p 
                    INNER JOIN cedir.paciente p2 ON p2.id_persona = p.id 
                    INNER JOIN cedir.paciente_protocolo pp ON pp.id_paciente = p2.id 
                    INNER JOIN cedir.protocolo pr ON pr.id = pp.id_protocolo
                    WHERE LOWER(p.nombre) LIKE :busqueda 
                       OR LOWER(p.apellido) LIKE :busqueda
                    LIMIT 1
                """
                result = conn.execute(text(query_like), {'busqueda': f'%{nombre_limpio}%'})
                row = result.fetchone()

                if row:
                    logger.info(f"✅ Paciente encontrado (LIKE): {row[0]} {row[1]} -> Protocolo: {row[2]}")
                    return {
                        'nombre': row[0],
                        'apellido': row[1],
                        'protocolo': row[2],
                        'protocolo_id': row[3],
                        'persona_id': row[4],
                        'nombre_completo': f"{row[0]} {row[1]}"
                    }

                logger.warning(f"❌ No se encontró paciente para: '{nombre_busqueda}'")
                return None

        except Exception as e:
            logger.error(f"Error buscando paciente: {e}")
            return None
    
    # ============ MÉTODOS DE ACTUALIZACIÓN ============
    
    def update_ticket_protocolo(self, ticket_id: int, paciente_nombre: str) -> bool:
        """Actualiza el protocolo del ticket según el paciente"""
        # Buscar protocolo por paciente
        paciente_info = self.get_protocolo_by_paciente(paciente_nombre)

        if paciente_info and paciente_info.get('protocolo'):
            try:
                with self.engine.connect() as conn:
                    conn.execute(
                        text("UPDATE cedir.ticket SET protocolo = :protocolo WHERE id = :id"),
                        {'protocolo': paciente_info['protocolo'], 'id': ticket_id}
                    )
                    conn.commit()
                    logger.info(f"Protocolo '{paciente_info['protocolo']}' asignado al ticket {ticket_id}")
                    return True
            except Exception as e:
                logger.error(f"Error actualizando protocolo: {e}")

        return False
    
    def update_ticket_paciente(self, ticket_id: int, paciente_nombre: str, paciente_id: int = None) -> bool:
        """Actualiza el nombre del paciente en un ticket"""
        try:
            with self.engine.connect() as conn:
                conn.execute(
                    text("UPDATE cedir.ticket SET paciente = :paciente WHERE id = :id"),
                    {'paciente': paciente_nombre, 'id': ticket_id}
                )
                conn.commit()
                logger.info(f"Paciente actualizado para ticket {ticket_id}: {paciente_nombre}")
                return True
        except Exception as e:
            logger.error(f"Error actualizando paciente del ticket {ticket_id}: {e}")
            return False
        
    def get_protocolo_by_paciente(self, nombre: str, apellido: str = None) -> Dict[str, Any]:
        """
        Obtiene el protocolo asociado a un paciente

        Args:
            nombre: Nombre del paciente
            apellido: Apellido del paciente (opcional)

        Returns:
            Diccionario con protocolo y datos del paciente
        """
        try:
            with self.engine.connect() as conn:
                query = """
                    SELECT 
                        p.nombre, 
                        p.apellido, 
                        pr.identificador_protocolo,
                        pr.id as protocolo_id
                    FROM cedir.persona p 
                    INNER JOIN cedir.paciente p2 ON p2.id_persona = p.id 
                    INNER JOIN cedir.paciente_protocolo pp ON pp.id_paciente = p2.id 
                    INNER JOIN cedir.protocolo pr ON pr.id = pp.id_protocolo
                    WHERE p.nombre ILIKE :nombre
                """
                params = {'nombre': f'%{nombre}%'}

                if apellido:
                    query += " AND p.apellido ILIKE :apellido"
                    params['apellido'] = f'%{apellido}%'

                result = conn.execute(text(query), params)
                row = result.fetchone()

                if row:
                    return {
                        'nombre': row[0],
                        'apellido': row[1],
                        'protocolo': row[2],
                        'protocolo_id': row[3]
                    }
                return None
        except Exception as e:
            logger.error(f"Error obteniendo protocolo por paciente: {e}")
            return None
        
        
    def match_protocolos_batch(self, textos: List[str], threshold: float = 0.7) -> List[Dict]:
        """
        Busca múltiples protocolos en lote (útil para logging y auditoría)

        Args:
            textos: Lista de textos a buscar
            threshold: Umbral de similitud

        Returns:
            Lista de diccionarios con resultados
        """
        if not textos:
            return []

        protocolos_db = self.get_all_protocolos()
        results = []

        for texto in textos:
            result = {
                'input': texto,
                'matched': None,
                'exact_match': False,
                'similarity': 0
            }

            if not texto:
                results.append(result)
                continue
            
            texto_lower = texto.strip().lower()

            # Búsqueda exacta
            for p in protocolos_db:
                if p and p.lower() == texto_lower:
                    result['matched'] = p
                    result['exact_match'] = True
                    result['similarity'] = 1.0
                    break
                
            # Búsqueda por similitud
            if not result['matched']:
                best_match = None
                best_ratio = 0
                for p in protocolos_db:
                    if not p:
                        continue
                    ratio = SequenceMatcher(None, texto_lower, p.lower()).ratio()
                    if ratio > best_ratio and ratio >= threshold:
                        best_ratio = ratio
                        best_match = p

                if best_match:
                    result['matched'] = best_match
                    result['similarity'] = best_ratio

            results.append(result)

            # Loggear resultados no encontrados
            if not result['matched']:
                logger.warning(f"Protocolo no encontrado en batch: '{texto}'")

        # Resumen del batch
        encontrados = sum(1 for r in results if r['matched'])
        logger.info(f"Batch processing: {encontrados}/{len(results)} protocolos encontrados")

        return results
    
    def buscar_paciente_protocolo_avanzado(self, nombre_busqueda: str) -> Dict[str, Any]:
        """
        Busca un paciente por nombre usando algoritmo de matching avanzado

        Args:
            nombre_busqueda: Nombre completo o parcial (ej: "farias esica", "esica farias")

        Returns:
            Diccionario con datos del paciente y protocolo
        """
        if not nombre_busqueda:
            return None

        try:
            with self.engine.connect() as conn:
                nombre_limpio = nombre_busqueda.strip()

                # Dividir en posible nombre y apellido
                partes = nombre_limpio.split()
                nombre_part = partes[0] if partes else ''
                apellido_part = ' '.join(partes[1:]) if len(partes) > 1 else ''

                # Consulta SQL con matching avanzado
                query = """
                    WITH pacientes_norm AS (
                        SELECT 
                            p.id as persona_id,
                            p.nombre,
                            p.apellido,
                            pr.identificador_protocolo,
                            pr.id as protocolo_id,
                            -- Normalizar para matching
                            LOWER(p.nombre) as nombre_norm,
                            LOWER(p.apellido) as apellido_norm,
                            LOWER(CONCAT(p.nombre, ' ', p.apellido)) as nombre_completo_norm,
                            -- Calcular similarity
                            similarity(LOWER(p.nombre), LOWER(:nombre_busqueda)) as sim_nombre,
                            similarity(LOWER(p.apellido), LOWER(:nombre_busqueda)) as sim_apellido,
                            similarity(LOWER(CONCAT(p.nombre, ' ', p.apellido)), LOWER(:nombre_busqueda)) as sim_completo
                        FROM cedir.persona p 
                        INNER JOIN cedir.paciente p2 ON p2.id_persona = p.id 
                        INNER JOIN cedir.paciente_protocolo pp ON pp.id_paciente = p2.id 
                        INNER JOIN cedir.protocolo pr ON pr.id = pp.id_protocolo
                    )
                    SELECT 
                        persona_id,
                        nombre,
                        apellido,
                        identificador_protocolo,
                        protocolo_id,
                        nombre_completo_norm,
                        CASE
                            -- Coincidencia exacta de apellido y nombre
                            WHEN apellido_norm = LOWER(:apellido_busqueda) 
                                 AND nombre_norm = LOWER(:nombre_busqueda) THEN 100
                            -- Coincidencia exacta de apellido y nombre parcial
                            WHEN apellido_norm = LOWER(:apellido_busqueda) 
                                 AND (nombre_norm LIKE '%' || LOWER(:nombre_busqueda) || '%'
                                      OR LOWER(:nombre_busqueda) LIKE '%' || nombre_norm || '%') THEN 97
                            -- Coincidencia exacta de apellido y primera palabra del nombre
                            WHEN apellido_norm = LOWER(:apellido_busqueda) 
                                 AND split_part(nombre_norm, ' ', 1) = split_part(LOWER(:nombre_busqueda), ' ', 1) THEN 95
                            -- Coincidencia exacta de apellido y similitud alta de nombre
                            WHEN apellido_norm = LOWER(:apellido_busqueda) 
                                 AND sim_nombre > 0.85 THEN 93
                            -- Coincidencia exacta de apellido y similitud media de nombre
                            WHEN apellido_norm = LOWER(:apellido_busqueda) 
                                 AND sim_nombre > 0.60 THEN 85
                            -- Coincidencia por nombre completo
                            WHEN sim_completo > 0.80 THEN 90
                            -- Coincidencia solo por apellido
                            WHEN sim_apellido > 0.85 THEN 80
                            -- Coincidencia solo por nombre
                            WHEN sim_nombre > 0.85 THEN 75
                            -- Coincidencia parcial por cualquier campo
                            WHEN sim_completo > 0.60 THEN 70
                            ELSE ROUND((sim_completo * 100)::NUMERIC, 2)
                        END AS score,
                        sim_nombre,
                        sim_apellido,
                        sim_completo
                    FROM pacientes_norm
                    WHERE 
                        -- Filtros iniciales para mejorar performance
                        apellido_norm = LOWER(:apellido_busqueda)
                        OR sim_apellido > 0.60
                        OR sim_completo > 0.60
                    ORDER BY score DESC, sim_completo DESC
                    LIMIT 1
                """

                params = {
                    'nombre_busqueda': nombre_limpio.lower(),
                    'apellido_busqueda': apellido_part.lower() if apellido_part else nombre_part.lower()
                }

                result = conn.execute(text(query), params)
                row = result.fetchone()

                if row:
                    score = row[6]  # El score está en la posición 6 (index 5 si empezamos en 0)
                    logger.info(f"✅ Paciente encontrado: {row[1]} {row[2]} -> "
                               f"Protocolo: {row[3]} | Score: {score}")

                    # Si el score es muy bajo, considerar no encontrado
                    if score < 60:
                        logger.warning(f"⚠️ Score bajo ({score}) para coincidencia: {nombre_busqueda}")
                        return None

                    return {
                        'nombre': row[1],
                        'apellido': row[2],
                        'protocolo': row[3],
                        'protocolo_id': row[4],
                        'persona_id': row[0],
                        'nombre_completo': f"{row[1]} {row[2]}",
                        'score': score
                    }

                logger.warning(f"❌ No se encontró paciente para: {nombre_busqueda}")
                return None

        except Exception as e:
            logger.error(f"Error en búsqueda avanzada: {e}")
            return None
    
    # ============ MÉTODOS DE VALIDACIÓN PARA PROCESAMIENTO ============
    
    def validate_and_correct_ticket_data(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida y corrige los datos. Si encuentra al paciente, devuelve el nombre corregido.
        Si no lo encuentra, marca el ticket para NO insertar.
        """
        nombre_extraido = ticket_data.get('paciente', {}).get('nombre', '')

        if not nombre_extraido:
            logger.warning("No se extrajo nombre de paciente - Ticket no se insertará")
            ticket_data['paciente']['encontrado'] = False
            return ticket_data

        # Probar diferentes variantes del nombre
        variantes = [
            nombre_extraido,
            nombre_extraido.title(),
            nombre_extraido.lower(),
            ' '.join(reversed(nombre_extraido.strip().split()))
        ]

        paciente_info = None
        for variante in set(variantes):
            logger.info(f"Buscando variante: '{variante}'")
            paciente_info = self.buscar_paciente_protocolo_avanzado(variante)
            if paciente_info:
                break
            
        if paciente_info:
            # ✅ Paciente encontrado - usar nombre concatenado de la BD
            nombre_completo = f"{paciente_info['nombre']} {paciente_info['apellido']}"
            ticket_data['paciente']['nombre'] = nombre_completo
            ticket_data['paciente']['protocolo'] = paciente_info['protocolo']
            ticket_data['paciente']['persona_id'] = paciente_info['persona_id']
            ticket_data['paciente']['protocolo_id'] = paciente_info['protocolo_id']
            ticket_data['paciente']['encontrado'] = True
            ticket_data['paciente']['score'] = paciente_info.get('score', 0)

            logger.info(f"✅ Paciente ENCONTRADO: '{nombre_extraido}' -> '{nombre_completo}'")
            logger.info(f"📋 Protocolo: {paciente_info['protocolo']}")
            logger.info(f"📊 Ticket data después de validación: {ticket_data}")
            return ticket_data  # ← Asegurar que retorna ticket_data
        else:
            ticket_data['paciente']['encontrado'] = False
            logger.warning(f"❌ Paciente NO ENCONTRADO: '{nombre_extraido}'")
            return ticket_data 

        return ticket_data