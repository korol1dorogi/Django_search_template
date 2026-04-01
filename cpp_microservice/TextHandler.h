#pragma once
#include "json.hpp"

class TextHandler {
public:
    static nlohmann::json process(const std::string& input);
};