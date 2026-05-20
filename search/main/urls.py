from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('validate-query/', views.validate_query, name='validate_query'),
    path('download/<int:doc_id>/', views.download_document, name='download_document'),
]