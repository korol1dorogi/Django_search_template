import logging
from django.shortcuts import render
from .forms import UploadFileForm
from .models import Document, Term, DocumentTerm
from .search_engine import SearchEngine
from .tasks import process_uploaded_file

logger = logging.getLogger(__name__)

def index(request):
    context = {}
    if request.method == 'POST':
        if 'search' in request.POST:
            # --- Поиск ---
            search_query = request.POST.get('search_query', '').strip()
            if not search_query:
                context['search_message'] = 'Введите поисковый запрос.'
            else:
                engine = SearchEngine(search_query)
                docs = engine.get_matching_documents()
                if docs.exists():
                    results = []
                    if engine.is_simple_term:
                        # Простой запрос – добавляем частоты
                        term_str = engine.tokens[0][1]
                        try:
                            term_obj = Term.objects.get(term=term_str)
                            freq_map = dict(
                                DocumentTerm.objects
                                .filter(term=term_obj, document__in=docs)
                                .values_list('document_id', 'frequency')
                            )
                        except Term.DoesNotExist:
                            freq_map = {}
                        for doc in docs:
                            results.append({
                                'doc_name': doc.original_file_name,
                                'frequency': freq_map.get(doc.id, 0),
                                'uploaded_at': doc.uploaded_at,
                                'file_url': doc.file.url,
                            })
                    else:
                        # Сложный запрос – без частоты
                        for doc in docs:
                            results.append({
                                'doc_name': doc.original_file_name,
                                'frequency': None,
                                'uploaded_at': doc.uploaded_at,
                                'file_url': doc.file.url,
                            })
                    context['search_results'] = results
                    context['search_query'] = search_query
                else:
                    context['search_results'] = []
                    context['search_query'] = search_query
                    context['search_message'] = 'Ничего не найдено.'

        elif 'upload' in request.POST:
            # --- Загрузка файла ---
            form = UploadFileForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded_file = request.FILES['file']
                # Создаём документ с FileField, файл физически сохраняется в MEDIA_ROOT/uploads/
                doc = Document.objects.create(
                    file=uploaded_file,
                    original_file_name=uploaded_file.name
                )
                # Запускаем асинхронную обработку через Celery
                process_uploaded_file.delay(doc.id)
                context['upload_message'] = (
                    f'Файл "{uploaded_file.name}" загружен и поставлен в очередь на обработку.'
                )
            else:
                context['form_errors'] = form.errors
    else:
        # GET – просто показываем форму
        pass

    context['form'] = UploadFileForm()
    return render(request, 'main/index.html', context)