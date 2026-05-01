import requests
import logging
from celery import shared_task
from .models import Document, Term, DocumentTerm
from .utils import extract_text_from_file

logger = logging.getLogger(__name__)

@shared_task
def process_uploaded_file(document_id):
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error("Документ с id=%s не найден", document_id)
        return

    file_path = doc.file.path
    text = extract_text_from_file(file_path)

    if not text.strip():
        logger.warning("Не удалось извлечь текст из файла %s (id=%s)", doc.original_file_name, document_id)
        return

    try:
        response = requests.post(
            'http://localhost:8080/process',
            json={'text': text},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            terms_freq = data.get('result', {})
            for term_str, freq in terms_freq.items():
                # Терм уже в нижнем регистре из микросервиса, но сохраняем для надёжности
                term, _ = Term.objects.get_or_create(term=term_str.lower())
                DocumentTerm.objects.create(
                    document=doc,
                    term=term,
                    frequency=freq
                )
            doc.processed = True
            doc.save(update_fields=['processed'])
            logger.info("Файл %s успешно обработан, id=%s", doc.original_file_name, document_id)
        else:
            logger.error(
                "Ошибка микросервиса при обработке файла %s (id=%s): статус %d, тело: %s",
                doc.original_file_name, document_id,
                response.status_code, response.text
            )
    except requests.exceptions.RequestException as e:
        logger.exception("Ошибка соединения с микросервисом при обработке файла id=%s", document_id)