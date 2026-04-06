import os
import json
import requests
from django.shortcuts import render
from django.conf import settings
from .forms import UploadFileForm
from .models import Document, Term, DocumentTerm
from .utils import extract_text_from_file
from .search_engine import SearchEngine
import re

def index(request):
    context = {}
    if request.method == 'POST':
        if 'search' in request.POST:
            search_query = request.POST.get('search_query', '').strip()
            if not search_query:
                context['search_message'] = 'Введите поисковый запрос.'
            else:
                # Пытаемся интерпретировать как логический запрос
                engine = SearchEngine(search_query)
                docs = engine.get_matching_documents()
                if docs.exists():
                    # Для отображения в шаблоне преобразуем в список словарей
                    results = []
                    # Если запрос состоит из одного терма (простой поиск) — добавим частоту
                    # Для простоты определим, является ли запрос одним словом без операторов
                    is_simple_term = re.match(r'^\w+$', search_query, re.UNICODE) is not None
                    if is_simple_term:
                        # Найдём частоту для каждого документа
                        try:
                            term_obj = Term.objects.get(term=search_query.lower())
                            doc_terms = DocumentTerm.objects.filter(term=term_obj, document__in=docs)
                            freq_dict = {dt.document_id: dt.frequency for dt in doc_terms}
                        except Term.DoesNotExist:
                            freq_dict = {}
                        for doc in docs:
                            results.append({
                                'doc_name': doc.file_name,
                                'frequency': freq_dict.get(doc.id, 0),
                                'uploaded_at': doc.uploaded_at,
                                'file_path': doc.file_path,
                            })
                    else:
                        # Сложный запрос – показываем только документы без частоты
                        for doc in docs:
                            results.append({
                                'doc_name': doc.file_name,
                                'frequency': None,  # в шаблоне проверим
                                'uploaded_at': doc.uploaded_at,
                                'file_path': doc.file_path,
                            })
                    context['search_results'] = results
                    context['search_query'] = search_query
                else:
                    context['search_results'] = []
                    context['search_query'] = search_query
                    context['search_message'] = 'Ничего не найдено.'
        elif 'upload' in request.POST:
            form = UploadFileForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded_file = request.FILES['file']
                file_name = uploaded_file.name
                # Сохранение файла
                file_path = os.path.join(settings.MEDIA_ROOT, 'uploads', file_name)
                with open(file_path, 'wb+') as dest:
                    for chunk in uploaded_file.chunks():
                        dest.write(chunk)

                # Извлечение текста
                text = extract_text_from_file(file_path)
                if not text.strip():
                    context['upload_message'] = 'Не удалось извлечь текст из файла (возможно, пустой или неподдерживаемый формат).'
                else:
                    # Отправка в микросервис
                    try:
                        response = requests.post('http://localhost:8080/process', json={'text': text})
                        if response.status_code == 200:
                            data = response.json()
                            terms_freq = data.get('result', {})
                            # Сохранение документа
                            doc = Document.objects.create(
                                file_name=file_name,
                                file_path=os.path.join('uploads', file_name)
                            )
                            # Сохранение термов и связей
                            for term_str, freq in terms_freq.items():
                                term, _ = Term.objects.get_or_create(term=term_str)
                                DocumentTerm.objects.create(
                                    document=doc,
                                    term=term,
                                    frequency=freq
                                )
                            context['upload_message'] = f'Файл "{file_name}" успешно загружен и обработан.'
                        else:
                            context['upload_message'] = f'Ошибка при обращении к микросервису (статус {response.status_code}).'
                    except requests.exceptions.RequestException as e:
                        context['upload_message'] = f'Ошибка соединения с микросервисом: {e}'
            else:
                context['form_errors'] = form.errors
        else:
            pass

    context['form'] = UploadFileForm()
    return render(request, 'main/index.html', context)