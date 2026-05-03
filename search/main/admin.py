from django.contrib import admin
from django.db.models import Count, Q
from django.utils.html import format_html
from .models import Document, Term, DocumentTerm, TermRelation


class DocumentTermInline(admin.TabularInline):
    model = DocumentTerm
    extra = 0  # не показывать пустые строки
    fields = ('term', 'frequency')
    readonly_fields = ('term', 'frequency')  # если не планируем редактировать вручную
    can_delete = False
    show_change_link = True  # ссылка на изменение самого DocumentTerm

    def has_add_permission(self, request, obj=None):
        return False  # запрещаем добавлять записи через inline (управляется системой)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'original_file_name',
        'uuid_short',
        'processed_status',
        'uploaded_at_formatted',
        'file_link',
        'terms_count'
    )
    list_filter = ('processed', 'uploaded_at')
    search_fields = ('original_file_name', 'uuid')
    readonly_fields = ('uuid', 'uploaded_at', 'processed', 'file_preview')
    date_hierarchy = 'uploaded_at'
    inlines = [DocumentTermInline]

    fieldsets = (
        ('Основная информация', {
            'fields': ('uuid', 'original_file_name', 'file', 'file_preview', 'uploaded_at', 'processed')
        }),
    )

    def uuid_short(self, obj):
        """Показываем первые 8 символов UUID для краткости"""
        return str(obj.uuid)[:8]
    uuid_short.short_description = 'UUID (сокр.)'

    def processed_status(self, obj):
        """Цветной индикатор обработки"""
        if obj.processed:
            return format_html('<span style="color: green;">✓ Обработан</span>')
        return format_html('<span style="color: orange;">⏳ Ожидает</span>')
    processed_status.short_description = 'Статус'

    def uploaded_at_formatted(self, obj):
        return obj.uploaded_at.strftime('%d.%m.%Y %H:%M')
    uploaded_at_formatted.short_description = 'Загружен'
    uploaded_at_formatted.admin_order_field = 'uploaded_at'

    def file_link(self, obj):
        """Ссылка на скачивание файла"""
        if obj.file:
            return format_html('<a href="{}" target="_blank">📄 Скачать</a>', obj.file.url)
        return '-'
    file_link.short_description = 'Файл'

    def file_preview(self, obj):
        """Предпросмотр файла в форме"""
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                obj.file.url,
                obj.file.name
            )
        return 'Нет файла'
    file_preview.short_description = 'Текущий файл'

    def terms_count(self, obj):
        """Количество уникальных терминов, связанных с документом"""
        count = getattr(obj, '_terms_count', None)
        if count is None:
            count = DocumentTerm.objects.filter(document=obj).count()
        return count
    terms_count.short_description = 'Терминов в документе'
    terms_count.admin_order_field = '_terms_count'  # можно сортировать через аннотацию

    def get_queryset(self, request):
        """Аннотируем количество терминов для сортировки и отображения"""
        qs = super().get_queryset(request)
        return qs.annotate(_terms_count=Count('documentterm'))

    def has_delete_permission(self, request, obj=None):
        return True  # или по условию


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ('term', 'documents_count', 'total_frequency', 'has_relations')
    search_fields = ('term',)
    readonly_fields = ('documents_count', 'total_frequency', 'relations_list')

    def documents_count(self, obj):
        """Количество документов, содержащих этот терм"""
        return DocumentTerm.objects.filter(term=obj).count()
    documents_count.short_description = 'Документов с термом'

    def total_frequency(self, obj):
        """Суммарная частота по всем документам"""
        from django.db.models import Sum
        result = DocumentTerm.objects.filter(term=obj).aggregate(s=Sum('frequency'))
        return result['s'] or 0
    total_frequency.short_description = 'Суммарная частота'

    def has_relations(self, obj):
        """Есть ли связи с другими термами"""
        has = TermRelation.objects.filter(Q(term1=obj) | Q(term2=obj)).exists()
        if has:
            return format_html('<span style="color: blue;">✓</span>')
        return '-'
    has_relations.short_description = 'Связи'

    def relations_list(self, obj):
        """Отображает в форме связи этого терма с другими"""
        relations = TermRelation.objects.filter(Q(term1=obj) | Q(term2=obj)).select_related('term1', 'term2')
        if not relations:
            return 'Нет связей'
        items = []
        for r in relations:
            other = r.term2 if r.term1 == obj else r.term1
            items.append(f'{other.term} (вес: {r.weight:.4f})')
        return format_html('<br>'.join(items))
    relations_list.short_description = 'Связи с другими термами'

    fieldsets = (
        ('Терм', {
            'fields': ('term',)
        }),
        ('Статистика', {
            'fields': ('documents_count', 'total_frequency', 'relations_list')
        }),
    )


@admin.register(DocumentTerm)
class DocumentTermAdmin(admin.ModelAdmin):
    list_display = ('document_name', 'term_name', 'frequency')
    search_fields = ('document__original_file_name', 'term__term')
    list_filter = ('document__processed',)
    raw_id_fields = ('document', 'term')  # для больших объёмов
    list_select_related = ('document', 'term')  # оптимизация запросов

    def document_name(self, obj):
        return obj.document.original_file_name
    document_name.short_description = 'Документ'
    document_name.admin_order_field = 'document__original_file_name'

    def term_name(self, obj):
        return obj.term.term
    term_name.short_description = 'Терм'
    term_name.admin_order_field = 'term__term'


@admin.register(TermRelation)
class TermRelationAdmin(admin.ModelAdmin):
    list_display = ('term1_name', 'term2_name', 'weight')
    search_fields = ('term1__term', 'term2__term')
    raw_id_fields = ('term1', 'term2')
    list_filter = ('weight',)
    list_select_related = ('term1', 'term2')

    def term1_name(self, obj):
        return obj.term1.term
    term1_name.short_description = 'Терм 1'
    term1_name.admin_order_field = 'term1__term'

    def term2_name(self, obj):
        return obj.term2.term
    term2_name.short_description = 'Терм 2'
    term2_name.admin_order_field = 'term2__term'

    # Дополнительно: автоматическое упорядочивание при создании через админку
    # уже реализовано в модели, но можно дополнительно сообщить.
    def save_model(self, request, obj, form, change):
        # Модель сама упорядочит, но на всякий случай оставим вызов родного save
        super().save_model(request, obj, form, change)