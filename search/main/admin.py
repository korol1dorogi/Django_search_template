import math
from django.contrib import admin
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.html import format_html
from .models import Document, Term, DocumentTerm, TermRelation, TermRelationArchive
from .tasks import process_uploaded_file

PHI = (1 + math.sqrt(5)) / 2  # ≈ 1.618033...


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
    change_list_template = 'admin/main/document/change_list.html'
    change_form_template = 'admin/main/document/change_form.html'
    actions = ['retry_processing']

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
        return True

    @admin.action(description='Повторить обработку выбранных документов')
    def retry_processing(self, request, queryset):
        count = 0
        for doc in queryset:
            doc.processed = False
            doc.save(update_fields=['processed'])
            process_uploaded_file.delay(doc.id)
            count += 1
        self.message_user(request, f'{count} документ(ов) поставлено в очередь на повторную обработку.')

    def get_urls(self):
        custom = [
            path('wipe/', self.admin_site.admin_view(self.wipe_view),
                 name='main_document_wipe'),
            path('<int:object_id>/retry/', self.admin_site.admin_view(self.retry_view),
                 name='main_document_retry'),
        ]
        return custom + super().get_urls()

    def retry_view(self, request, object_id):
        if request.method != 'POST':
            return HttpResponseRedirect('../../')
        doc = get_object_or_404(Document, pk=object_id)
        doc.processed = False
        doc.save(update_fields=['processed'])
        process_uploaded_file.delay(doc.id)
        self.message_user(request, f'Документ «{doc.original_file_name}» поставлен в очередь на повторную обработку.')
        return HttpResponseRedirect('../../')

    def wipe_view(self, request):
        if request.method != 'POST':
            return HttpResponseRedirect('../')

        # Удаляем физические файлы
        for doc in Document.objects.all():
            try:
                doc.file.delete(save=False)
            except Exception:
                pass

        # Очищаем все прикладные таблицы в безопасном порядке
        TermRelationArchive.objects.all().delete()
        TermRelation.objects.all().delete()
        DocumentTerm.objects.all().delete()
        Document.objects.all().delete()
        Term.objects.all().delete()

        self.message_user(request, 'Все документы, термины и связи удалены. Пользователи и служебные таблицы Django сохранены.')
        return HttpResponseRedirect('../')


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
    list_display = ('term1_name', 'term2_name', 'weight_display')
    search_fields = ('term1__term', 'term2__term')
    raw_id_fields = ('term1', 'term2')
    ordering = ('-weight',)
    list_select_related = ('term1', 'term2')
    change_list_template = 'admin/main/termrelation/change_list.html'

    # ------------------------------------------------------------------
    # Отображение
    # ------------------------------------------------------------------

    def term1_name(self, obj):
        return obj.term1.term
    term1_name.short_description = 'Терм 1'
    term1_name.admin_order_field = 'term1__term'

    def term2_name(self, obj):
        return obj.term2.term
    term2_name.short_description = 'Терм 2'
    term2_name.admin_order_field = 'term2__term'

    def weight_display(self, obj):
        color = 'green' if obj.weight >= 1.0 else ('gray' if obj.weight > 0 else 'red')
        return format_html('<span style="color:{}">{}</span>', color, f'{obj.weight:.4f}')
    weight_display.short_description = 'Вес'
    weight_display.admin_order_field = 'weight'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

    # ------------------------------------------------------------------
    # Статистика для шаблона
    # ------------------------------------------------------------------

    def changelist_view(self, request, extra_context=None):
        total = TermRelation.objects.count()
        keep = math.floor(total / PHI) if total else 0
        extra_context = extra_context or {}
        extra_context.update({
            'total_relations': total,
            'archive_count': TermRelationArchive.objects.count(),
            'compress_delete_count': total - keep,
            'compress_keep_count': keep,
            'can_compress': total > 1,
        })
        return super().changelist_view(request, extra_context=extra_context)

    # ------------------------------------------------------------------
    # Кастомные URL-маршруты
    # ------------------------------------------------------------------

    def get_urls(self):
        custom = [
            path('compress/', self.admin_site.admin_view(self.compress_view),
                 name='main_termrelation_compress'),
            path('restore/', self.admin_site.admin_view(self.restore_view),
                 name='main_termrelation_restore'),
        ]
        return custom + super().get_urls()

    # ------------------------------------------------------------------
    # φ-компрессия
    # ------------------------------------------------------------------

    def compress_view(self, request):
        if request.method != 'POST':
            return HttpResponseRedirect('../')

        total = TermRelation.objects.count()
        if total < 2:
            self.message_user(request, 'Недостаточно связей для сжатия.', level='WARNING')
            return HttpResponseRedirect('../')

        keep = math.floor(total / PHI)
        delete_count = total - keep

        # Берём delete_count записей с наименьшим весом
        to_delete = list(
            TermRelation.objects
            .order_by('weight', 'id')
            .values('id', 'term1_id', 'term2_id')[:delete_count]
        )

        # Архивируем (ignore_conflicts — если пара уже в архиве, не падаем)
        TermRelationArchive.objects.bulk_create(
            [TermRelationArchive(term1_id=r['term1_id'], term2_id=r['term2_id'])
             for r in to_delete],
            ignore_conflicts=True,
        )

        # Удаляем из основной таблицы
        TermRelation.objects.filter(id__in=[r['id'] for r in to_delete]).delete()

        self.message_user(
            request,
            f'Сжатие выполнено: удалено {delete_count} связей из {total}, '
            f'осталось {keep}. Удалённые пары сохранены в архив.',
        )
        return HttpResponseRedirect('../')

    # ------------------------------------------------------------------
    # Восстановление
    # ------------------------------------------------------------------

    def restore_view(self, request):
        if request.method != 'POST':
            return HttpResponseRedirect('../')

        archives = list(TermRelationArchive.objects.values('term1_id', 'term2_id'))
        if not archives:
            self.message_user(request, 'Архив пуст — нечего восстанавливать.', level='WARNING')
            return HttpResponseRedirect('../')

        restored = 0
        for arch in archives:
            t1_id, t2_id = arch['term1_id'], arch['term2_id']
            # Гарантируем канонический порядок (как в TermRelation.save)
            if t1_id > t2_id:
                t1_id, t2_id = t2_id, t1_id
            _, created = TermRelation.objects.get_or_create(
                term1_id=t1_id,
                term2_id=t2_id,
                defaults={'weight': 1.0},
            )
            if created:
                restored += 1

        TermRelationArchive.objects.all().delete()

        skipped = len(archives) - restored
        msg = f'Восстановлено {restored} связей (вес = 1.0).'
        if skipped:
            msg += f' Пропущено {skipped} — уже существуют в таблице.'
        self.message_user(request, msg)
        return HttpResponseRedirect('../')


@admin.register(TermRelationArchive)
class TermRelationArchiveAdmin(admin.ModelAdmin):
    list_display = ('term1_name', 'term2_name', 'compressed_at')
    list_select_related = ('term1', 'term2')
    search_fields = ('term1__term', 'term2__term')
    readonly_fields = ('term1', 'term2', 'compressed_at')

    def term1_name(self, obj):
        return obj.term1.term
    term1_name.short_description = 'Терм 1'

    def term2_name(self, obj):
        return obj.term2.term
    term2_name.short_description = 'Терм 2'

    def has_add_permission(self, request):
        return False