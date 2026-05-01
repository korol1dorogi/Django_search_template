#include "TextHandler.h"
#include <cstddef>
#include <cstring>  
#include <cstdlib>   
#include <cctype>    
#include <cstdint>

// Макрос для передачи массива и его размера (должен быть определён ДО первого использования)
#define SUF(arr) arr, sizeof(arr)/sizeof(arr[0])

// ---------------------------------------------------------------------------
// Вспомогательные UTF-8 примитивы (без STL)
// ---------------------------------------------------------------------------

// Длина многобайтовой последовательности по первому байту (возвращает 1-4, 0 для некорректного)
static int utf8_char_len(unsigned char c) {
    if (c < 0x80) return 1;
    if (c < 0xC0) return 0;
    if (c < 0xE0) return 2;
    if (c < 0xF0) return 3;
    if (c < 0xF8) return 4;
    return 0;
}

// Читает следующий code point, двигает указатель p вперёд.
static unsigned int next_codepoint(const char*& p) {
    unsigned char c = *p;
    int len = utf8_char_len(c);
    unsigned int cp = 0;
    if (len == 0) { ++p; return 0xFFFD; }           // замена ошибочного байта
    if (len == 1) { cp = c; ++p; return cp; }
    cp = c & (0xFF >> len);
    for (int i = 1; i < len; ++i) {
        unsigned char next = (unsigned char)p[i];
        if ((next & 0xC0) != 0x80) { p += i; return 0xFFFD; }
        cp = (cp << 6) | (next & 0x3F);
    }
    p += len;
    return cp;
}

// Записывает code point в виде UTF-8 в переданный буфер (должен быть не менее 4 байт),
// возвращает количество записанных байт.
static int write_utf8(unsigned int cp, char* out) {
    if (cp < 0x80) {
        out[0] = (char)cp;
        return 1;
    } else if (cp < 0x800) {
        out[0] = (char)(0xC0 | (cp >> 6));
        out[1] = (char)(0x80 | (cp & 0x3F));
        return 2;
    } else if (cp < 0x10000) {
        out[0] = (char)(0xE0 | (cp >> 12));
        out[1] = (char)(0x80 | ((cp >> 6) & 0x3F));
        out[2] = (char)(0x80 | (cp & 0x3F));
        return 3;
    } else if (cp < 0x110000) {
        out[0] = (char)(0xF0 | (cp >> 18));
        out[1] = (char)(0x80 | ((cp >> 12) & 0x3F));
        out[2] = (char)(0x80 | ((cp >> 6) & 0x3F));
        out[3] = (char)(0x80 | (cp & 0x3F));
        return 4;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// Нижний регистр для кириллицы + ASCII (в терминах code points)
// ---------------------------------------------------------------------------
static unsigned int to_lower_cp(unsigned int cp) {
    // ASCII заглавные
    if (cp >= 'A' && cp <= 'Z') return cp + ('a' - 'A');
    // Кириллица: Ё -> ё
    if (cp == 0x0401) return 0x0451;
    // А-Я -> а-я
    if (cp >= 0x0410 && cp <= 0x042F)
        return cp + (0x0430 - 0x0410);
    // Историческая кириллица (чётные коды заглавные, нечётные строчные)
    if (cp >= 0x0460 && cp <= 0x0481) {
        if (cp % 2 == 0) return cp + 1;
    }
    // Остальное не меняем
    return cp;
}

// ---------------------------------------------------------------------------
// Проверки классов символов для токенизации
// ---------------------------------------------------------------------------
static bool is_letter_or_digit_cp(unsigned int cp) {
    // ASCII цифры
    if (cp >= '0' && cp <= '9') return true;
    // Латинские заглавные и строчные
    if ((cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z')) return true;
    // Основная кириллица (0400–04FF)
    if (cp >= 0x0400 && cp <= 0x04FF) return true;
    // Расширенная кириллица (0500–052F)
    if (cp >= 0x0500 && cp <= 0x052F) return true;
    return false;
}

// ---------------------------------------------------------------------------
// Определение наличия кириллицы в слове (UTF-8 строка)
// ---------------------------------------------------------------------------
bool contains_cyrillic(const char* word) {
    const char* p = word;
    while (*p) {
        unsigned int cp = next_codepoint(p);
        if ((cp >= 0x0400 && cp <= 0x04FF) || (cp >= 0x0500 && cp <= 0x052F))
            return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// Стеммер Портера для английского (полноценный, без STL)
// Возвращает строку в куче, которую нужно освободить вызывающему.
// ---------------------------------------------------------------------------

typedef enum { VOWEL = 1, CONSONANT = 2 } letter_type;

static letter_type letter_ascii(char c) {
    if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u') return VOWEL;
    if (c == 'y') return CONSONANT; // будет переопределяться по месту
    return CONSONANT;
}

// Проверка, содержит ли слово гласную внутри заданного диапазона
static int contains_vowel(const char* word, size_t start, size_t end) {
    for (size_t i = start; i < end; ++i) {
        char c = word[i];
        if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u')
            return 1;
        if (c == 'y' && i > start) { // y считается гласной только если не первая
            return 1;
        }
    }
    return 0;
}

// Проверка, оканчивается ли слово на двойную согласную
static int ends_double_consonant(const char* word, size_t len) {
    if (len < 2) return 0;
    char last = word[len-1];
    char prev = word[len-2];
    if (last != prev) return 0;
    if (last == 'a'||last=='e'||last=='i'||last=='o'||last=='u'||last=='y') return 0;
    return 1;
}

// Проверка формы CVC, где последняя согласная не w, x, y
static int is_cvc(const char* word, size_t len) {
    if (len < 3) return 0;
    char c0 = word[len-3], c1 = word[len-2], c2 = word[len-1];
    if (c2 == 'w' || c2 == 'x' || c2 == 'y') return 0;
    // упрощённо: c1 == a/e/i/o/u/y (y считается гласной)
    if (c1=='a'||c1=='e'||c1=='i'||c1=='o'||c1=='u'||c1=='y') {
        if (c0!='a'&&c0!='e'&&c0!='i'&&c0!='o'&&c0!='u'&&c0!='y' &&
            c2!='a'&&c2!='e'&&c2!='i'&&c2!='o'&&c2!='u'&&c2!='y')
            return 1;
    }
    return 0;
}

// Мера m: число последовательностей VC
static int measure_m(const char* word, size_t len) {
    int m = 0;
    int state = 0; // 0 = ожидаем гласную, 1 = ожидаем согласную
    for (size_t i = 0; i < len; ++i) {
        char c = word[i];
        int is_vowel = (c=='a'||c=='e'||c=='i'||c=='o'||c=='u'||(c=='y'&&i>0));
        if (state == 0) {
            if (is_vowel) state = 1;
        } else {
            if (!is_vowel) {
                ++m;
                state = 0;
            }
        }
    }
    return m;
}

// Удаление суффикса вручную (изменяет длину len)
static int replace_suffix(char* word, size_t* len, const char* suffix, size_t suff_len,
                           int min_m) {
    size_t l = *len;
    if (l < suff_len) return 0;
    if (strncmp(word + l - suff_len, suffix, suff_len) != 0) return 0;
    // Проверка m перед удалением
    if (min_m >= 0 && measure_m(word, l - suff_len) < min_m) return 0;
    *len = l - suff_len;
    word[*len] = '\0';
    return 1;
}

char* stem_english(const char* word_utf8) {
    // Работаем с латинским словом; копируем в буфер.
    size_t cap = strlen(word_utf8) + 1;
    char* word = (char*)malloc(cap);
    if (!word) return NULL;
    strcpy(word, word_utf8);
    size_t len = strlen(word);

    int changed = 1;
    while (changed) {
        changed = 0;
        // Шаг 1a
        if (len > 4 && strncmp(word+len-4, "sses", 4)==0) {
            len -= 2; word[len]='\0'; changed=1;
        } else if (len > 3 && (strncmp(word+len-3, "ies", 3)==0)) {
            len -= 2; word[len]='\0'; changed=1;
        } else if (len > 2 && word[len-1]=='s' && word[len-2]!='s') {
            if (len > 2 && word[len-2]!='u' && word[len-2]!='s') { // пропускаем us/ss
                len -= 1; word[len]='\0'; changed=1;
            }
        }
        // Шаг 1b
        if (len > 4 && strncmp(word+len-3, "eed", 3)==0) {
            if (measure_m(word, len-3) > 0) {
                len -= 1; word[len]='\0'; changed=1;
            }
        } else if ((len > 2 && strncmp(word+len-2, "ed", 2)==0) ||
                   (len > 3 && strncmp(word+len-3, "ing", 3)==0)) {
            size_t off = (word[len-1]=='g') ? 3 : 2; // ing/ed
            if (contains_vowel(word, 0, len - off)) {
                len -= off; word[len]='\0'; changed=1;
                // дополнительные окончания
                if (len > 1 && (word[len-1]=='a'||word[len-1]=='o'||word[len-1]=='e')) {
                    if (word[len-2] == word[len-1]) { // удвоение
                        len -= 1; word[len]='\0';
                    }
                }
                if (len >= 2 && word[len-1]=='l' && word[len-2]=='l' && measure_m(word,len)>1) {
                    // оставляем пока
                }
                if (len > 1 && word[len-1]=='y' && measure_m(word,len)>0) {
                    word[len-1] = 'i';
                }
                if (len > 1 && word[len-1]=='c' && word[len-2]=='c') {
                    word[len-1] = '\0'; len--;
                }
            }
        }
        // Шаг 1c
        if (len > 0 && word[len-1]=='y' && contains_vowel(word,0,len-1)) {
            word[len-1]='i'; changed=1;
        }
    }

    char* result = (char*)malloc(len+1);
    if (result) memcpy(result, word, len+1);
    free(word);
    return result;
}

// ---------------------------------------------------------------------------
// Стеммер русского языка (Snowball, переписанный вручную без STL)
// Возвращает строку в куче.
// ---------------------------------------------------------------------------
static bool russian_is_vowel(unsigned int cp) {
    return (cp == 0x0430 || cp == 0x0435 || cp == 0x0451 || cp == 0x0438 ||
            cp == 0x043E || cp == 0x0443 || cp == 0x044B || cp == 0x044D ||
            cp == 0x044E || cp == 0x044F);
}
static bool russian_is_soft(unsigned int cp) { return cp == 0x044C; } // ь
static bool russian_is_hard(unsigned int cp) { return cp == 0x044A; } // ъ

// Преобразование UTF-8 слова в массив code points (ручное выделение памяти)
static unsigned int* word_to_codepoints(const char* word, size_t* count) {
    size_t cap = 16, size = 0;
    unsigned int* arr = (unsigned int*)malloc(cap * sizeof(unsigned int));
    if (!arr) return NULL;
    const char* p = word;
    while (*p) {
        unsigned int cp = next_codepoint(p);
        if (size == cap) {
            cap *= 2;
            unsigned int* tmp = (unsigned int*)realloc(arr, cap * sizeof(unsigned int));
            if (!tmp) { free(arr); return NULL; }
            arr = tmp;
        }
        arr[size++] = cp;
    }
    *count = size;
    return arr;
}

// Преобразование массива code points обратно в UTF-8 строку (куча)
static char* codepoints_to_utf8(unsigned int* arr, size_t size) {
    // Сначала посчитаем длину в байтах
    size_t byte_len = 0;
    for (size_t i = 0; i < size; ++i) {
        unsigned int cp = arr[i];
        if (cp < 0x80) byte_len += 1;
        else if (cp < 0x800) byte_len += 2;
        else if (cp < 0x10000) byte_len += 3;
        else if (cp < 0x110000) byte_len += 4;
    }
    char* result = (char*)malloc(byte_len + 1);
    if (!result) return NULL;
    char* out = result;
    for (size_t i = 0; i < size; ++i) {
        int n = write_utf8(arr[i], out);
        out += n;
    }
    *out = '\0';
    return result;
}

// Найти RV (после первой гласной)
static size_t rv_rus(unsigned int* w, size_t len) {
    for (size_t i = 0; i < len; ++i)
        if (russian_is_vowel(w[i]))
            return i + 1;
    return len;
}

// Удалить суффикс, представленный массивом code points, из слова w длиной wlen,
// если после удаления длина не меньше min_len и удаление происходит в зоне до zone_end.
// Возвращает новую длину (0 = неудача)
static size_t try_delete_suffix(unsigned int* w, size_t wlen,
                                const unsigned int* suffix, size_t suff_len,
                                size_t min_len, size_t zone_end) {
    if (wlen < suff_len) return 0;
    if (wlen - suff_len < min_len) return 0;
    if (wlen - suff_len > zone_end) zone_end = wlen;
    for (size_t i = 0; i < suff_len; ++i) {
        if (w[wlen - suff_len + i] != suffix[i])
            return 0;
    }
    // Успех – возвращаем новую длину
    return wlen - suff_len;
}

// Удалить "ь" в конце
static size_t remove_soft_rus(unsigned int* w, size_t len) {
    if (len > 0 && w[len-1] == 0x044C) return len-1;
    return len;
}

// Заменить "ий" на "ь"
static size_t replace_ii_soft(unsigned int* w, size_t len) {
    if (len >= 2 && w[len-2] == 0x0438 && w[len-1] == 0x0439) {
        w[len-2] = 0x044C;
        return len-1;
    }
    return len;
}

char* stem_russian(const char* word) {
    size_t wlen = 0;
    unsigned int* w = word_to_codepoints(word, &wlen);
    if (!w) return NULL;

    // Приведение к нижнему регистру
    for (size_t i = 0; i < wlen; ++i)
        w[i] = to_lower_cp(w[i]);

    size_t rv = rv_rus(w, wlen);
    size_t i;
    // Шаг 1: возвратные частицы и совершенный вид
    // удалим "ся"
    wlen = remove_soft_rus(w, wlen);
    {
        unsigned int tmp[] = {0x0441,0x044F}; // ся
        i = try_delete_suffix(w, wlen, SUF(tmp), rv, wlen);
        if (i) wlen = i;
    }
    wlen = remove_soft_rus(w, wlen);

    // совершенный вид
    int done = 0;
    if (!done) {
        unsigned int suff[] = {0x0432}; // в
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; done = 1; }
    }
    if (!done) {
        unsigned int suff[] = {0x0432,0x0448,0x0438}; // вши
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; done = 1; }
    }
    if (!done) {
        unsigned int suff[] = {0x0432,0x0448,0x0438,0x0441,0x044C}; // вшись
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; done = 1; }
    }
    if (!done) {
        unsigned int suff[] = {0x0438,0x0432}; // ив
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; done = 1; }
    }
    if (!done) {
        unsigned int suff[] = {0x0438,0x0432,0x0448,0x0438}; // ивши
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; done = 1; }
    }
    if (!done) {
        unsigned int suff[] = {0x0438,0x0432,0x0448,0x0438,0x0441,0x044C}; // ившись
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; done = 1; }
    }
    if (!done) {
        unsigned int suff[] = {0x044B,0x0432}; // ыв
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; done = 1; }
    }
    if (!done) {
        unsigned int suff[] = {0x044B,0x0432,0x0448,0x0438}; // ывши
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; done = 1; }
    }
    if (!done) {
        unsigned int suff[] = {0x044B,0x0432,0x0448,0x0438,0x0441,0x044C}; // ывшись
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; done = 1; }
    }
    if (done) goto step4;

    // Шаг 2: прилагательные/причастия
    {
        unsigned int suff[] = {0x0438,0x043C,0x0438}; // ими
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; goto step2_done; }
    }
    {
        unsigned int suff[] = {0x044B,0x043C,0x0438}; // ыми
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) { wlen = i; goto step2_done; }
    }
    {
        unsigned int suff[] = {0x0435,0x0433,0x043E}; // его
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x043E,0x0433,0x043E}; // ого
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0435,0x043C,0x0443}; // ему
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x043E,0x043C,0x0443}; // ому
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0438,0x0445}; // их
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x044B,0x0445}; // ых
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0435,0x0435}; // ее
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0438,0x0435}; // ие
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x044B,0x0435}; // ые
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x043E,0x0435}; // ое
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0435,0x0439}; // ей
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0438,0x0439}; // ий
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x044B,0x0439}; // ый
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x043E,0x0439}; // ой
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0435,0x043C}; // ем
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0438,0x043C}; // им
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x044B,0x043C}; // ым
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x043E,0x043C}; // ом
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }

 step2_done:
    {
        unsigned int suff[] = {0x044C}; // ь
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    wlen = replace_ii_soft(w, wlen);
    wlen = replace_ii_soft(w, wlen);
    // Переход к шагу 3

    // Шаг 3: окончания на и/ы
    {
        unsigned int suff[] = {0x0438}; // и
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) {
            wlen = i;
            wlen = replace_ii_soft(w, wlen);
            wlen = replace_ii_soft(w, wlen);
            goto step3_end;
        }
    }
    {
        unsigned int suff[] = {0x044B}; // ы
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) {
            wlen = i;
            wlen = replace_ii_soft(w, wlen);
            wlen = replace_ii_soft(w, wlen);
            goto step3_end;
        }
    }
    goto step4;

 step3_end:
    // удаление ость и ейш/ейше
    {
        unsigned int suff[] = {0x043E,0x0441,0x0442,0x044C}; // ость
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0435,0x0439,0x0448}; // ейш
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    {
        unsigned int suff[] = {0x0435,0x0439,0x0448,0x0435}; // ейше
        i = try_delete_suffix(w, wlen, SUF(suff), rv, wlen);
        if (i) wlen = i;
    }
    wlen = remove_soft_rus(w, wlen);
    wlen = replace_ii_soft(w, wlen);
    wlen = replace_ii_soft(w, wlen);

 step4:
    // Удаление нн/н
    if (wlen > 0 && w[wlen-1] == 0x043D) { // 'н'
        if (wlen > 1 && w[wlen-2] == 0x043D) {
            wlen -= 2;
        } else {
            wlen -= 1;
        }
    }
    wlen = remove_soft_rus(w, wlen);

    char* result = codepoints_to_utf8(w, wlen);
    free(w);
    return result;
}

// ---------------------------------------------------------------------------
// хранение частоты вхождения терм(пока что слов) в документ
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Основная функция обработки текста
// ---------------------------------------------------------------------------
nlohmann::json TextHandler::process(const std::string& input) {
    WordArray words;
    initWordArray(&words);

    // Буфер для накопления символов текущего слова (UTF-8, поэтому 1024 байт достаточно)
    char buffer[1024];
    size_t pos = 0;   // позиция в buffer (байты)

    const char* p = input.c_str();
    while (*p) {
        // запоминаем начало текущего байта
        const char* start = p;
        unsigned int cp = next_codepoint(p); // p уже сдвинулось
        int bytelen = (int)(p - start);

        if (is_letter_or_digit_cp(cp)) {
            // Если влезает в буфер – копируем байты
            if (pos + bytelen < sizeof(buffer)) {
                memcpy(buffer + pos, start, bytelen);
                pos += bytelen;
            } else {
                // Слово слишком длинное, игнорируем остаток
                // В базовой версии о дальнейших символах забываем, можно закостылить в целом решение, но я не знаю ни об одном слове длиной больше даже 254 символов, поэтому смысла нет
            }
        } else {
            // Найден разделитель – конец слова
            if (pos > 0) {
                buffer[pos] = '\0';

                // Определяем, русское слово или нет, и вызываем соответствующий стеммер
                char* stem = NULL;
                if (contains_cyrillic(buffer)) {
                    stem = stem_russian(buffer);
                } else {
                    stem = stem_english(buffer);
                }
                if (stem) {
                    int idx = findWord(&words, stem);
                    if (idx == -1) {
                        addWord(&words, stem);
                    } else {
                        incWord(&words, idx);
                    }
                    free(stem);
                }
                pos = 0;
            }
        }
    }
    // Если текст заканчивается на слове
    if (pos > 0) {
        buffer[pos] = '\0';
        char* stem = contains_cyrillic(buffer) ? stem_russian(buffer) : stem_english(buffer);
        if (stem) {
            int idx = findWord(&words, stem);
            if (idx == -1) {
                addWord(&words, stem);
            } else {
                incWord(&words, idx);
            }
            free(stem);
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