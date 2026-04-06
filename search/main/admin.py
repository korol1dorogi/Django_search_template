from django.contrib import admin
from .models import Term, DocumentTerm, Document
# Register your models here.

admin.site.register(Term)
admin.site.register(DocumentTerm)
admin.site.register(Document)