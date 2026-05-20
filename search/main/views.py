import logging
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, FileResponse
from django.db.models import Q, F
from django.views.decorators.http import require_GET
from .search_parser import parse_search_query, QuerySyntaxError
from .forms import UploadFileForm, ALLOWED_EXTENSIONS
from .models import Document, Term, DocumentTerm, TermRelation
from .search_engine import SearchEngine
from .tasks import process_uploaded_file
from .stopwords import STOPWORDS

logger = logging.getLogger(__name__)

# Веса операторов для матрицы смежности
_OPERATOR_WEIGHTS = {
    'AND': 1.0,
    'OR': 0.3,
    'AND_NOT': -0.5,
}


def update_term_relations_from_query(tokens):
    """
    Обновляет TermRelation на основе операторов между соседними термами в запросе.

    AND  → +1.0
    OR   → +0.3
    AND NOT → -0.5
    """
    term_positions = [(i, val) for i, (typ, val) in enumerate(tokens) if typ == SearchEngine.TOKEN_TERM]

    for k in range(len(term_positions) - 1):
        pos_a, term_a = term_positions[k]
        pos_b, term_b = term_positions[k + 1]

        ops = {typ for typ, _ in tokens[pos_a + 1:pos_b]}

        if SearchEngine.TOKEN_AND in ops and SearchEngine.TOKEN_NOT in ops:
            delta = _OPERATOR_WEIGHTS['AND_NOT']
        elif SearchEngine.TOKEN_AND in ops:
            delta = _OPERATOR_WEIGHTS['AND']
        elif SearchEngine.TOKEN_OR in ops:
            delta = _OPERATOR_WEIGHTS['OR']
        else:
            continue

        if term_a in STOPWORDS or term_b in STOPWORDS:
            continue

        try:
            t1 = Term.objects.get(term=term_a)
            t2 = Term.objects.get(term=term_b)
        except Term.DoesNotExist:
            continue

        if t1.id > t2.id:
            t1, t2 = t2, t1

        rel, created = TermRelation.objects.get_or_create(
            term1=t1, term2=t2, defaults={'weight': delta}
        )
        if not created:
            TermRelation.objects.filter(pk=rel.pk).update(weight=F('weight') + delta)


def get_related_terms(stemmed_terms, limit=8):
    """Возвращает термины, наиболее связанные с переданными через матрицу смежности."""
    term_objs = Term.objects.filter(term__in=stemmed_terms)
    if not term_objs.exists():
        return []
    relations = (
        TermRelation.objects
        .filter(Q(term1__in=term_objs) | Q(term2__in=term_objs))
        .select_related('term1', 'term2')
        .order_by('-weight')[:limit * 4]
    )
    stemmed_set = set(stemmed_terms)
    seen = {}
    for rel in relations:
        for t in (rel.term1.term, rel.term2.term):
            if t not in stemmed_set and t not in seen and t not in STOPWORDS:
                seen[t] = rel.weight
    return sorted(seen, key=lambda t: -seen[t])[:limit]


def index(request):
    context = {}
    if request.method == 'POST':
        if 'search' in request.POST:
            # --- Поиск ---
            search_query = request.POST.get('search_query', '').strip()
            try:
                parse_search_query(search_query)
            except QuerySyntaxError as e:
                context['search_message'] = f'Ошибка в запросе: {e}'
                context['search_query'] = search_query
                context['form'] = UploadFileForm()
                return render(request, 'main/index.html', context)
            if not search_query:
                context['search_message'] = 'Введите поисковый запрос.'
            else:
                engine = SearchEngine(search_query)
                # Обновляем матрицу смежности по оператором запроса
                if not engine.is_simple_term:
                    update_term_relations_from_query(engine.tokens)
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
                                'doc_id': doc.id,
                                'doc_name': doc.original_file_name,
                                'frequency': freq_map.get(doc.id, 0),
                                'uploaded_at': doc.uploaded_at,
                            })
                    else:
                        # Сложный запрос – без частоты
                        for doc in docs:
                            results.append({
                                'doc_id': doc.id,
                                'doc_name': doc.original_file_name,
                                'frequency': None,
                                'uploaded_at': doc.uploaded_at,
                            })
                    context['search_results'] = results
                    context['search_query'] = search_query
                    stemmed_terms = [val for typ, val in engine.tokens if typ == engine.TOKEN_TERM]
                    context['related_terms'] = get_related_terms(stemmed_terms)
                else:
                    context['search_results'] = []
                    context['search_query'] = search_query
                    context['search_message'] = 'Ничего не найдено.'

        elif 'upload' in request.POST:
            # --- Пакетная загрузка файлов ---
            uploaded_files = request.FILES.getlist('file')
            if not uploaded_files:
                context['form_errors'] = {'file': ['Выберите хотя бы один файл.']}
            else:
                max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 50 * 1024 * 1024)
                ok, errors = [], []
                for f in uploaded_files:
                    ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
                    if ext not in ALLOWED_EXTENSIONS:
                        errors.append(f'«{f.name}»: недопустимый формат.')
                        continue
                    if f.size > max_size:
                        errors.append(f'«{f.name}»: превышен лимит {max_size // (1024*1024)} МБ.')
                        continue
                    doc = Document.objects.create(file=f, original_file_name=f.name)
                    process_uploaded_file.delay(doc.id)
                    ok.append(f.name)
                if ok:
                    context['upload_message'] = (
                        f'Загружено {len(ok)} файл(ов) и поставлено в очередь: {", ".join(ok)}.'
                    )
                if errors:
                    context['form_errors'] = {'file': errors}
    else:
        # GET – просто показываем форму
        pass

    context['form'] = UploadFileForm()
    return render(request, 'main/index.html', context)


def download_document(request, doc_id):
    doc = get_object_or_404(Document, id=doc_id)
    return FileResponse(
        doc.file.open('rb'),
        as_attachment=True,
        filename=doc.original_file_name,
    )


@require_GET
def validate_query(request):
    query = request.GET.get('query', '')
    if not query.strip():
        return JsonResponse({'valid': True, 'message': 'Пустой запрос'})
    try:
        parse_search_query(query)
        return JsonResponse({'valid': True, 'message': 'Запрос корректен'})
    except QuerySyntaxError as e:
        return JsonResponse({'valid': False, 'message': str(e)})