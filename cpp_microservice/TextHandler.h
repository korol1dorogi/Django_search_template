#pragma once
#include "json.hpp"

class TextHandler {
public:
    static nlohmann::json process(const std::string& input);
};

bool contains_cyrillic(const char* word);
char* stem_russian(const char* word);
char* stem_english(const char* word);