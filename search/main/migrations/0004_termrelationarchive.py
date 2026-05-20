import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0003_termrelation_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TermRelationArchive',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('compressed_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('term1', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='+',
                    to='main.term',
                )),
                ('term2', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='+',
                    to='main.term',
                )),
            ],
            options={
                'unique_together': {('term1', 'term2')},
            },
        ),
    ]
