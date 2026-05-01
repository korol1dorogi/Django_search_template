Компонент	        Порт	Назначение
Redis (брокер)	    6379	Передача задач между Django и Celery
C++ микросервис	    8080	Обработка текста (POST /process)
Celery worker	     –	    Асинхронная обработка загруженных файлов
Django dev сервер	8000	Веб-интерфейс и поиск


Создание и активация виртуального окружения Python
Windows (cmd):
python -m venv venv
venv\Scripts\activate


Linux:
bash
python3 -m venv venv
source venv/bin/activate

Зависимости:
pip install -r requirements.txt

Если файла нет или устаревшая версия:

bash
pip install django celery redis requests python-docx PyPDF2 ebooklib


Установка и запуск Redis
Windows
Скачайте и установите Memurai (https://www.memurai.com/).

После установки сервис Redis запускается автоматически (проверка: в Memurai Command Prompt выполните memurai-cli ping, должен быть PONG).

Если сервис не стартует, запустите Memurai из меню Пуск.

Linux
Установите Redis из репозитория:

bash
sudo apt update
sudo apt install redis-server
Запустите и включите автозапуск:

bash
sudo systemctl start redis
sudo systemctl enable redis
Проверка:

bash
redis-cli ping

Сборка и запуск C++ микросервиса
4.1. Зависимости
Компилятор C++17 (gcc ≥ 8 или clang, Visual Studio 2019+).

Библиотеки:

cpp-httplib – заголовочный файл httplib.h.

nlohmann/json – заголовочный файл json.hpp.

Файлы main.cpp, TextHandler.h, TextHandler.cpp.

Положите httplib.h и json.hpp в папку с проектом (или в системный include path).

4.2. Компиляция (Windows, Visual Studio Developer Command Prompt)
cmd
cl /EHsc /std:c++17 main.cpp TextHandler.cpp /Fe:microservice.exe
Или используйте CMake, или откройте проект в Visual Studio с настройкой стандарта C++17.

4.3. Компиляция (Linux, g++)
bash
g++ -std=c++17 -pthread main.cpp TextHandler.cpp -o microservice
Если nlohmann/json не в системном пути, добавьте -I/path/to/json.

Для cpp-httplib требуется -pthread (на Linux). На Windows может потребоваться ws2_32.lib дополнительно (обычно в Visual Studio это подхватывается).

Запуск Celery worker
Для запуска необходим открытый терминал в корне проекта (где manage.py). Виртуальное окружение должно быть активно.

Windows
cmd
celery -A search worker --loglevel=info --pool=solo
-A search – замените search на имя пакета с celery.py.

--pool=solo – обязательно под Windows, чтобы избежать проблем с fork.

При успехе вы увидите зарегистрированные задачи (в том числе main.tasks.process_uploaded_file).

Linux
bash
celery -A search worker --loglevel=info
На Linux пул prefork работает, но можно оставить без указания.

6. Запуск Django dev-сервера
Откройте ещё один терминал из корня проекта, активируйте виртуальное окружение.

bash
python manage.py runserver
Теперь сервер доступен на http://127.0.0.1:8000.

7. Порядок запуска всего стека (краткая шпаргалка)
Redis – должен работать в фоне (служба Windows или systemd Linux).

C++ микросервис – запустите в терминале или в IDE.

Celery worker – отдельный терминал, команда celery -A search worker ....

Django – ещё один терминал, python manage.py runserver.

Для остановки:

Остановите Django (Ctrl+C).

Остановите Celery worker (Ctrl+C).

Остановите C++ микросервис (Ctrl+C) или через IDE.

Redis можно не выключать.

8. Проверка полного цикла
Откройте браузер на http://127.0.0.1:8000.

Загрузите файл (например, test.txt).

В логах Celery worker появится сообщение о получении задачи и (при успехе) о завершении.

После обработки в интерфейсе можно выполнить поиск по словам из файла.
