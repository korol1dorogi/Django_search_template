#include "httplib.h"
#include "json.hpp"
#include "TextHandler.h"

#include <iostream>
#include <csignal>
#include <cstdlib>
#include <atomic>
#include <ctime>
#include <thread>
#include <chrono>

using json = nlohmann::json;

std::atomic<bool> shutdown_flag(false);
httplib::Server* g_server = nullptr;

void signal_handler(int sig) {
    std::cout << "[INFO] Received signal " << sig << ", initiating graceful shutdown..." << std::endl;
    shutdown_flag = true;
    if (g_server) {
        g_server->stop(); // Останавливаем приём новых соединений
    }
}

int main() {
    // 1. Настройка сигналов
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    // 2. Чтение переменных окружения
    int port = 8080;
    if (const char* env_port = std::getenv("PORT")) {
        port = std::stoi(env_port);
    }

    int thread_pool_size = 0;
    if (const char* env_threads = std::getenv("THREAD_POOL_SIZE")) {
        thread_pool_size = std::stoi(env_threads);
    } else {
        thread_pool_size = std::thread::hardware_concurrency();
        if (thread_pool_size == 0) thread_pool_size = 4;
    }

    int max_concurrent = 0;
    if (const char* env_max = std::getenv("MAX_CONCURRENT_REQUESTS")) {
        max_concurrent = std::stoi(env_max);
    }

    // 3. Создание сервера
    httplib::Server svr;
    g_server = &svr;

    // Настройка пула потоков
    svr.new_task_queue = [thread_pool_size] {
        return new httplib::ThreadPool(thread_pool_size);
    };

    // Опциональное ограничение параллельных запросов (семафор)
    std::unique_ptr<std::counting_semaphore<>> sem;
    if (max_concurrent > 0) {
        sem = std::make_unique<std::counting_semaphore<>>(max_concurrent);
        std::cout << "[INFO] Limiting concurrent requests to " << max_concurrent << std::endl;
    }

    // 4. Healthcheck endpoint
    svr.Get("/health", [](const httplib::Request&, httplib::Response& res) {
        json resp = {
            {"status", "ok"},
            {"timestamp", std::time(nullptr)}
        };
        res.set_content(resp.dump(), "application/json");
    });

    // Алиас /ping для совместимости
    svr.Get("/ping", [](const httplib::Request&, httplib::Response& res) {
        json resp = {{"status", "ok"}};
        res.set_content(resp.dump(), "application/json");
    });

    // 5. Обработка текста (синхронно)
    svr.Post("/process", [&](const httplib::Request& req, httplib::Response& res) {
        // Если есть ограничение, захватываем семафор
        if (sem) sem->acquire();

        // Автоматический release при выходе из scope
        auto release_sem = [&] {
            if (sem) sem->release();
        };
        std::unique_lock<std::mutex> lock; // не используем мьютекс, но для удобства можно обернуть
        // Для простоты обернём вызов в try-catch с гарантией release
        try {
            auto req_json = json::parse(req.body);
            if (!req_json.contains("text") || !req_json["text"].is_string()) {
                res.status = 400;
                res.set_content(R"({"error":"Missing 'text' field"})", "application/json");
                release_sem();
                return;
            }
            std::string input = req_json["text"].get<std::string>();
            std::string result = TextHandler::process(input);
            json resp = {{"result", result}};
            res.set_content(resp.dump(), "application/json");
        } catch (const std::exception& e) {
            res.status = 400;
            res.set_content(R"({"error":"Invalid JSON"})", "application/json");
        }
        release_sem();
    });

    // 6. Запуск сервера
    std::cout << "[INFO] Server starting on port " << port << std::endl;
    std::cout << "[INFO] Thread pool size: " << thread_pool_size << std::endl;
    std::cout << "[INFO] Health check: /health, /ping" << std::endl;
    std::cout << "[INFO] Text processing: POST /process with JSON {\"text\":\"...\"}" << std::endl;

    // Запускаем слушатель в отдельном потоке, чтобы можно было проверять флаг завершения
    std::thread server_thread([&svr, port]() {
        svr.listen("0.0.0.0", port);
    });

    // Ожидаем сигнал завершения
    while (!shutdown_flag) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    std::cout << "[INFO] Shutting down..." << std::endl;
    svr.stop(); // уже вызвано в сигнале, но на всякий случай
    server_thread.join();
    std::cout << "[INFO] Server stopped." << std::endl;

    return 0;
}
