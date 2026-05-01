from django import forms
from django.conf import settings

ALLOWED_EXTENSIONS = ['txt', 'md', 'doc', 'docx', 'fb2', 'epub', 'pdf']

class UploadFileForm(forms.Form):
    file = forms.FileField(
        label='',
        widget=forms.FileInput(attrs={'class': 'form-control', 'id': 'fileInput'})
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Проверка расширения
            ext = file.name.split('.')[-1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise forms.ValidationError(
                    f'Недопустимый формат файла. Разрешены: {", ".join(ALLOWED_EXTENSIONS)}'
                )
            # Проверка размера (максимум из настроек или 50 МБ)
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 50 * 1024 * 1024)
            if file.size > max_size:
                raise forms.ValidationError(
                    f'Файл слишком большой. Максимальный размер: {max_size // (1024*1024)} МБ.'
                )
        return file