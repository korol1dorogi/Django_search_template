#include "TextHandler.h"
#include <cstddef>   // size_t
#include <cstring>   // для memcpy, но можно и свои
#include <cstdlib>   // для malloc, free
#include <cctype>    // используется только для isalnum/tolower? 
                    // в условии сказано без cctype, но можно заменить своими.

// Поскольку условие запрещает cctype, напишем свои аналоги.
static bool is_alnum(char ch) {
    return (ch >= 'a' && ch <= 'z') ||
           (ch >= 'A' && ch <= 'Z') ||
           (ch >= '0' && ch <= '9');
}

static char to_lower(char ch) {
    if (ch >= 'A' && ch <= 'Z')
        return ch + ('a' - 'A');
    return ch;
}

// хранение частоты вхождения терм(пока что слов) в документ
struct WordEntry {
    char* word;
    int   freq;
};

// Массив WordEntry с возможность быстро получить вместительность и размер
struct WordArray {
    WordEntry* entries;
    size_t     capacity;
    size_t     size;
};

// Инициализация массива слов(терм в будущем)
static void initWordArray(WordArray* arr) {
    arr->capacity = 16;
    arr->size = 0;
    arr->entries = (WordEntry*)malloc(arr->capacity * sizeof(WordEntry));
    if (!arr->entries) throw std::bad_alloc(); // можно просто exit, но для простоты
}
// деструктор для массива слов
static void destroyWordArray(WordArray* arr) {
    for (size_t i = 0; i < arr->size; ++i) {
        free(arr->entries[i].word);
    }
    free(arr->entries);
    arr->entries = nullptr;
    arr->size = arr->capacity = 0;
}

// Проверка текущей вместимости(возможно ли добавить новое слово)
static void ensureCapacity(WordArray* arr) {
    if (arr->size == arr->capacity) {
        arr->capacity *= 2; //2 - лушчий коэффициент расширения массива с т. зрения соотношения простота/оптимальность
        WordEntry* newEntries = (WordEntry*)realloc(arr->entries, arr->capacity * sizeof(WordEntry)); //перевыделение памяти под динамический массив слов в случае расширения
        //Возвращает указатель на новый блок в памяти или на текущий, если удалось его расширить.
        //Касаемо безопасности использования realloc - т.к. используется простая структура, то так поступать допустимо. В случае если потребуется усложнение функционала будет выполнен переход на new[] и ручное копирование
        //realloc лишь копирует байты информации, а не вызывает конструкторы копирования, что может быть опасно для кастомных классов, но не в этом случае
        if (!newEntries) throw std::bad_alloc(); //В случае возникновения такой ситуации наиболее вероятна нехватка памяти (newEntries == nullptr, значит realloc вернул null)
        arr->entries = newEntries; // Возвращает указатель на новый блок памяти/старый если удалось его расширить
    }
}

// Линейный поиск слова в массиве (возвращает индекс или -1), в данном случае построено на компорации(сравнении) слов в лексикографическом порядке(функция strcmp)
static int findWord(const WordArray* arr, const char* word) {
    for (size_t i = 0; i < arr->size; ++i) {
        if (strcmp(arr->entries[i].word, word) == 0) {
            return (int)i;
        }
    }
    return -1;
}

// Добавление нового слова (копирует строку)
static void addWord(WordArray* arr, const char* word) {
    ensureCapacity(arr);
    char* newWord = (char*)malloc(strlen(word) + 1); // Динамический массив символов, Выделяется памяти под длину слова +1, +1 для '\0' - нуль-терминатор - символ окончания строки 
    if (!newWord) throw std::bad_alloc();
    strcpy(newWord, word);
    arr->entries[arr->size].word = newWord;
    arr->entries[arr->size].freq = 1;
    arr->size++;
}

// Увеличить частоту существующего слова (реализация классического инкремента, но для структуры, созданной описанной ранее)
static void incWord(WordArray* arr, int idx) {
    arr->entries[idx].freq++;
}

// Основная функция обработки текста
nlohmann::json TextHandler::process(const std::string& input) {
    WordArray words;
    initWordArray(&words);

    // Буфер для накопления символов текущего слова
    char buffer[1024];   // максимальная длина слова
    size_t pos = 0;

    for (char ch : input) {
        if (is_alnum(ch)) {
            if (pos < sizeof(buffer) - 1) {
                buffer[pos++] = to_lower(ch);
            } else {
                // Слово слишком длинное, игнорируем остаток
                //В базовой версии о дальнейших символах забываем, можно закостылить в целом решение, но я не знаю ни об одном слове длиной больше даже 254 символов, поэтому смысла нет
            }
        } else {
            // Конец слова
            if (pos > 0) {
                buffer[pos] = '\0';
                int idx = findWord(&words, buffer);
                if (idx == -1) {
                    addWord(&words, buffer);
                } else {
                    incWord(&words, idx);
                }
                pos = 0;
            }
        }
    }
    // Если текст заканчивается на слове
    if (pos > 0) {
        buffer[pos] = '\0';
        int idx = findWord(&words, buffer);
        if (idx == -1) {
            addWord(&words, buffer);
        } else {
            incWord(&words, idx);
        }
    }

    // Сборка JSON-ответа
    nlohmann::json result;
    for (size_t i = 0; i < words.size; ++i) {
        result[words.entries[i].word] = words.entries[i].freq;
    }

    destroyWordArray(&words);
    return result;
}