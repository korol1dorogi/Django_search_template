from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('validate-query/', views.validate_query, name='validate_query'),
]