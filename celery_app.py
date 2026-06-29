import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

celery_app = Celery(
    'tickets',
    broker=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
    include=['tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Argentina/Buenos_Aires',
    enable_utc=True,
    task_track_started=True,
    task_store_errors_even_if_ignored=True,
    worker_concurrency=1,
)
