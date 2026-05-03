import re

class QuerySyntaxError(Exception):
    pass

TOKEN_AND = 'AND'
TOKEN_OR = 'OR'
TOKEN_NOT = 'NOT'
TOKEN_LPAREN = '('
TOKEN_RPAREN = ')'
TOKEN_TERM = 'TERM'

def parse_search_query(query: str):
    """
    Проверяет синтаксис поискового запроса.
    Если запрос корректен – ничего не возвращает.
    При ошибке выбрасывает QuerySyntaxError с описанием.
    """
    if not isinstance(query, str):
        raise QuerySyntaxError("Запрос должен быть строкой")
    query = query.strip()
    if not query:
        return  # пустой запрос допустим

    # Токенизация без стемминга
    tokens = _tokenize(query)

    # Проверка последовательности токенов
    _validate_sequence(tokens)


def _tokenize(query):
    """Лёгкая токенизация: возвращает список (type, value) без стемминга."""
    pattern = r'(\bAND\b|\bOR\b|\bNOT\b|[()]|\w+)'
    raw_tokens = re.findall(pattern, query, re.IGNORECASE)
    result = []
    for tok in raw_tokens:
        upper = tok.upper()
        if upper == 'AND':
            result.append((TOKEN_AND, None))
        elif upper == 'OR':
            result.append((TOKEN_OR, None))
        elif upper == 'NOT':
            result.append((TOKEN_NOT, None))
        elif tok == '(':
            result.append((TOKEN_LPAREN, None))
        elif tok == ')':
            result.append((TOKEN_RPAREN, None))
        else:
            # Терм – сохраняем как есть (без стемминга)
            result.append((TOKEN_TERM, tok))
    return result


def _validate_sequence(tokens):
    """
    Проверяет формальные правила:
    - Никаких двух операторов/скобок в недопустимых комбинациях.
    - Баланс скобок.
    - Оператор не может быть в начале/конце без операнда.
    - Нет пустых скобок.
    """
    if not tokens:
        return

    # 1. Первый и последний токены
    first_type = tokens[0][0]
    last_type = tokens[-1][0]
    if first_type in (TOKEN_AND, TOKEN_OR):
        raise QuerySyntaxError("Запрос не может начинаться с оператора AND или OR")
    if first_type == TOKEN_NOT and len(tokens) > 1 and tokens[1][0] not in (TOKEN_TERM, TOKEN_LPAREN):
        raise QuerySyntaxError("После NOT должно следовать слово или скобка")
    if last_type in (TOKEN_AND, TOKEN_OR, TOKEN_NOT):
        raise QuerySyntaxError("Запрос не может заканчиваться оператором")
    if last_type == TOKEN_LPAREN:
        raise QuerySyntaxError("Незакрытая скобка")

    # 2. Проверка всех пар соседних токенов
    for i in range(len(tokens) - 1):
        curr_type, curr_val = tokens[i]
        next_type, next_val = tokens[i + 1]

        # Два операнда подряд (слово и слово)
        if curr_type == TOKEN_TERM and next_type == TOKEN_TERM:
            raise QuerySyntaxError(
                f"Два слова подряд: '{curr_val} {next_val}'. Возможно, пропущен оператор AND или OR."
            )
        # Два бинарных оператора подряд
        if curr_type in (TOKEN_AND, TOKEN_OR) and next_type in (TOKEN_AND, TOKEN_OR):
            raise QuerySyntaxError(
                f"Нельзя ставить два оператора подряд: '{curr_type} {next_type}'"
            )
        # Оператор AND/OR перед закрывающей скобкой или концом
        if curr_type in (TOKEN_AND, TOKEN_OR) and next_type == TOKEN_RPAREN:
            raise QuerySyntaxError(
                f"Перед закрывающей скобкой не должно быть оператора '{curr_type}'"
            )
        # NOT перед закрывающей скобкой – допустимо? Да, но осторожно, если скобка пустая – отловим.
        # Открывающая скобка и сразу после неё AND/OR
        if curr_type == TOKEN_LPAREN and next_type in (TOKEN_AND, TOKEN_OR):
            raise QuerySyntaxError(
                f"После открывающей скобки не может стоять оператор '{next_type}'"
            )
        # Открывающая скобка и сразу закрывающая – пустые скобки
        if curr_type == TOKEN_LPAREN and next_type == TOKEN_RPAREN:
            raise QuerySyntaxError("Пустые скобки () недопустимы")

        # NOT может идти перед словом или открывающей скобкой – это ОК
        # Закрывающая скобка перед словом – ошибка
        if curr_type == TOKEN_RPAREN and next_type == TOKEN_TERM:
            raise QuerySyntaxError("После закрывающей скобки нельзя сразу писать слово без оператора")

    # 3. Баланс скобок (простой счётчик)
    balance = 0
    for tok_type, _ in tokens:
        if tok_type == TOKEN_LPAREN:
            balance += 1
        elif tok_type == TOKEN_RPAREN:
            balance -= 1
            if balance < 0:
                raise QuerySyntaxError("Лишняя закрывающая скобка")
    if balance > 0:
        raise QuerySyntaxError("Не хватает закрывающих скобок")

    # 4. NOT на конце – уже проверено, но повторим для ясности
    if tokens[-1][0] == TOKEN_NOT:
        raise QuerySyntaxError("Оператор NOT не может быть в конце запроса")