import math
import requests
import logging
from django.conf import settings
from django.db import transaction
from django.db.models import F
from celery import shared_task
from .models import Document, Term, DocumentTerm, TermRelation
from .utils import extract_text_from_file
from .stopwords import STOPWORDS

PHI = (1 + math.sqrt(5)) / 2

logger = logging.getLogger(__name__)

@shared_task
def process_uploaded_file(document_id):
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error("Документ с id=%s не найден", document_id)
        return

    # --- Проверка: если уже обработан, не трогаем (опционально) ---
    if doc.processed:
        logger.info("Документ %s уже обработан, пропускаем.", document_id)
        return

    file_path = doc.file.path
    text = extract_text_from_file(file_path)

    if not text.strip():
        logger.warning("Не удалось извлечь текст из файла %s (id=%s)", doc.original_file_name, document_id)
        return

    try:
        response = requests.post(
            settings.MICROSERVICE_PROCESS_URL,
            json={'text': text},
            timeout=120
        )
        if response.status_code == 200:
            data = response.json()
            result = data.get('result', {})

            # Фильтруем стоп-слова, числа и однобуквенные токены
            aggregated = {}
            for term, freq in result.items():
                term_lower = term.lower()
                if term_lower in STOPWORDS:
                    continue
                if term_lower.isdigit():
                    continue
                if len(term_lower) < 2:
                    continue
                aggregated[term_lower] = aggregated.get(term_lower, 0) + freq

            # Создаём Term-объекты до транзакции, чтобы не держать write-lock на SELECT+INSERT
            term_map = {}
            for term_str in aggregated:
                term_obj, _ = Term.objects.get_or_create(term=term_str)
                term_map[term_str] = term_obj

            # φ-отбор термов для матрицы смежности:
            # сортируем по частоте, берём топ ⌊K/φ⌋ (≈61.8% самых частых)
            sorted_terms = sorted(aggregated.items(), key=lambda x: -x[1])
            k = len(sorted_terms)
            top_n = max(2, math.floor(k / PHI))
            top_terms = [t for t, _ in sorted_terms[:top_n]]

            # Все записи в одной транзакции = один fsync вместо сотен
            with transaction.atomic():
                DocumentTerm.objects.filter(document=doc).delete()
                DocumentTerm.objects.bulk_create([
                    DocumentTerm(document=doc, term=term_map[t], frequency=f)
                    for t, f in aggregated.items()
                ])

                # Все пары среди топ-термов → TermRelation (weight += 1.0 за каждый документ)
                for i in range(len(top_terms)):
                    for j in range(i + 1, len(top_terms)):
                        t1 = term_map[top_terms[i]]
                        t2 = term_map[top_terms[j]]
                        if t1.id > t2.id:
                            t1, t2 = t2, t1
                        rel, created = TermRelation.objects.get_or_create(
                            term1=t1, term2=t2, defaults={'weight': 1.0}
                        )
                        if not created:
                            TermRelation.objects.filter(pk=rel.pk).update(weight=F('weight') + 1.0)

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