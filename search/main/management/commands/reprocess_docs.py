from django.core.management.base import BaseCommand
from main.models import Document, TermRelation
from main.tasks import process_uploaded_file


class Command(BaseCommand):
    help = 'Сбрасывает флаг processed и ставит все документы в очередь на повторную обработку'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-relations',
            action='store_true',
            help='Также очистить таблицу TermRelation перед переобработкой',
        )

    def handle(self, *args, **options):
        if options['clear_relations']:
            count = TermRelation.objects.count()
            TermRelation.objects.all().delete()
            self.stdout.write(f'Удалено {count} записей TermRelation.')

        docs = Document.objects.all()
        total = docs.count()
        if total == 0:
            self.stdout.write('Документов нет.')
            return

        docs.update(processed=False)
        for doc in docs:
            process_uploaded_file.delay(doc.id)

        self.stdout.write(self.style.SUCCESS(
            f'Поставлено в очередь {total} документов.'
        ))
