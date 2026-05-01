import os
from celery import Celery
from celery import shared_task

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'search.settings')

app = Celery('app')  # имя проекта
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
