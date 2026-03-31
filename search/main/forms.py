from django import forms
from .models import UploadedFile

ALLOWED_EXTENSIONS = ['txt', 'md', 'doc', 'docx', 'fb2', 'epub', 'pdf']

class UploadFileModelForm(forms.ModelForm):
    class Meta:
        model = UploadedFile
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control', 'id': 'fileInput'})
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            ext = file.name.split('.')[-1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise forms.ValidationError(
                    f'Недопустимый формат файла. Разрешены: {", ".join(ALLOWED_EXTENSIONS)}'
                )
        return file