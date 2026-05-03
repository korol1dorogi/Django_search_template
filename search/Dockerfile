FROM python:3.11-slim

# Предотвращает создание .pyc файлов
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Установка зависимостей
COPY requirements.md .
RUN pip install --no-cache-dir -r requirements.md

# Копируем весь проект
COPY . .

# Порт Django
EXPOSE 8000

# По умолчанию запускаем Django runserver (для разработки)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
