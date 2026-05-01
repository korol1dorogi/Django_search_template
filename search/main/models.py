import uuid
from django.db import models

class Document(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    file = models.FileField(upload_to='uploads/', max_length=500)
    original_file_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    def __str__(self):
        return self.original_file_name


class Term(models.Model):
    term = models.CharField(max_length=255, unique=True)

    def save(self, *args, **kwargs):
        self.term = self.term.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.term


class DocumentTerm(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    frequency = models.IntegerField()

    class Meta:
        unique_together = ('document', 'term')
        indexes = [
            models.Index(fields=['term', 'document']),
            models.Index(fields=['document', 'term']),
        ]


class TermRelation(models.Model):
    """
    Матрица смежности для отношений между термами.
    Хранит вес связи между парой термов. Пара всегда упорядочена
    по возрастанию id, чтобы избежать дублирования.
    """
    term1 = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='relations_as_term1')
    term2 = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='relations_as_term2')
    weight = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('term1', 'term2')

    def save(self, *args, **kwargs):
        # Упорядочиваем термы по id
        if self.term1_id and self.term2_id and self.term1_id > self.term2_id:
            self.term1, self.term2 = self.term2, self.term1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.term1} <-> {self.term2}: {self.weight}"