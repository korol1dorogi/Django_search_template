# Определяем корень проекта
$root = "C:\Users\User\Desktop\kursach_sakod\Django_search_template\search"

# Запуск C++ микросервиса (скомпилированный .exe)
$microservicePath = "C:\Users\User\Desktop\sakod_kursach\Django_search_template\build\cpp_microservice.exe"
Start-Process -FilePath $microservicePath -WindowStyle Minimized

# Запуск Celery
$celeryPath = "celery"
$celeryArgs = "-A search worker --loglevel=info --pool=solo"
Start-Process -FilePath $celeryPath -ArgumentList $celeryArgs -WindowStyle Minimized

# Запуск Django runserver
$djangoArgs = "manage.py runserver"
Start-Process -FilePath "python" -ArgumentList $djangoArgs -WindowStyle Minimized

Write-Host "Все компоненты запущены в фоне."
