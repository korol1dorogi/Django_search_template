from django.shortcuts import render
from .forms import UploadFileModelForm

def index(request):
    context = {}
    if request.method == 'POST':
        # Обработка поиска
        if 'search' in request.POST:
            search_query = request.POST.get('search_query', '')
            context['search_result'] = f'Вы искали: "{search_query}"'
            context['search_query'] = search_query  # чтобы сохранить значение в поле
        # Обработка загрузки файла
        elif 'upload' in request.POST:
            form = UploadFileModelForm(request.POST, request.FILES)
            if form.is_valid():
                form.save()
                context['upload_message'] = 'Файл успешно загружен.'
            else:
                context['form_errors'] = form.errors
        # Если кнопка не распознана, просто показываем форму
        else:
            pass

    # Для GET или после обработки передаём форму в контекст
    context['form'] = UploadFileModelForm()
    return render(request, 'main/index.html', context)