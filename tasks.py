import os
import logging
from celery_app import celery_app
from ticket_processor import TicketProcessor

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_tickets(self, file_path, usuario=None, schema='cedir', factura_referencia=None):
    api_key = os.environ.get('GEMINI_API_KEY', '')
    db_url = os.environ.get('DATABASE_URL', '')
    processed_folder = os.environ.get('PROCESSED_FOLDER', '/home/files/processed')
    prompts_folder = os.environ.get('PROMPTS_FOLDER', 'prompts')

    if not api_key or not db_url:
        raise ValueError("Faltan GEMINI_API_KEY o DATABASE_URL en el entorno")

    logger.info(f"Celery task iniciada: file={file_path}, usuario={usuario}")

    processor = TicketProcessor(
        api_key=api_key,
        db_connection_string=db_url,
        processed_folder=processed_folder,
        prompts_folder=prompts_folder,
        schema=schema
    )

    result = processor.process_multiple_tickets(
        file_path=file_path,
        usuario=usuario,
        move_to_processed=True,
        validate=True,
        factura_referencia=factura_referencia
    )

    logger.info(f"Celery task completada: {result.get('message', 'OK')}")
    return result
