from django.db import models

class Document(models.Model):
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file_name

class Term(models.Model):
    term = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.term

class DocumentTerm(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    frequency = models.IntegerField()

    class Meta:
        unique_together = ('document', 'term')