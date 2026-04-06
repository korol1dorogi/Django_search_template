import re
from collections import deque
from .models import Term, DocumentTerm, Document

class SearchEngine:
    """Парсер и вычислитель логических запросов (AND, OR, NOT) над документами."""

    TOKEN_AND = 'AND'
    TOKEN_OR = 'OR'
    TOKEN_NOT = 'NOT'
    TOKEN_LPAREN = '('
    TOKEN_RPAREN = ')'
    TOKEN_TERM = 'TERM'

    PRECEDENCE = {
        TOKEN_NOT: 3,
        TOKEN_AND: 2,
        TOKEN_OR: 1,
    }

    def __init__(self, query):
        self.query = query.strip()
        self.tokens = []
        self._tokenize()

    def _tokenize(self):
        """Разбивает строку запроса на токены."""
        pattern = r'(\bAND\b|\bOR\b|\bNOT\b|[()]|\w+)'
        raw_tokens = re.findall(pattern, self.query, re.IGNORECASE)
        for tok in raw_tokens:
            tok_upper = tok.upper()
            if tok_upper == 'AND':
                self.tokens.append((self.TOKEN_AND, None))
            elif tok_upper == 'OR':
                self.tokens.append((self.TOKEN_OR, None))
            elif tok_upper == 'NOT':
                self.tokens.append((self.TOKEN_NOT, None))
            elif tok == '(':
                self.tokens.append((self.TOKEN_LPAREN, None))
            elif tok == ')':
                self.tokens.append((self.TOKEN_RPAREN, None))
            else:
                self.tokens.append((self.TOKEN_TERM, tok.lower()))

    '''В обычной (инфиксной) записи операторы находятся между операндами, и есть скобки, меняющие приоритет. 
        Вычислять такое выражение напрямую неудобно – нужно учитывать кучу правил. 
        В постфиксной записи операторы идут после своих операндов, и скобки не нужны. 
        Вычисление происходит простым проходом слева направо с использованием стека.'''

    def _to_postfix(self):
        """Преобразует инфиксную последовательность в постфиксную (ОПН)."""
        output = []
        stack = []
        for token, value in self.tokens:
            if token == self.TOKEN_TERM:
                output.append((token, value))
            elif token == self.TOKEN_NOT:
                # унарный NOT
                while stack and stack[-1][0] == self.TOKEN_NOT:
                    output.append(stack.pop())
                stack.append((token, value))
            elif token in (self.TOKEN_AND, self.TOKEN_OR):
                while (stack and stack[-1][0] != self.TOKEN_LPAREN and
                       self.PRECEDENCE.get(stack[-1][0], 0) >= self.PRECEDENCE.get(token, 0)):
                    output.append(stack.pop())
                stack.append((token, value))
            elif token == self.TOKEN_LPAREN:
                stack.append((token, value))
            elif token == self.TOKEN_RPAREN:
                while stack and stack[-1][0] != self.TOKEN_LPAREN:
                    output.append(stack.pop())
                if stack and stack[-1][0] == self.TOKEN_LPAREN:
                    stack.pop()
                else:
                    raise ValueError("Несовпадение скобок")
        while stack:
            output.append(stack.pop())
        return output

    def _get_doc_set(self, term):
        """Возвращает множество ID документов, содержащих данный терм."""
        try:
            term_obj = Term.objects.get(term=term)
            doc_ids = DocumentTerm.objects.filter(term=term_obj).values_list('document_id', flat=True)
            return set(doc_ids)
        except Term.DoesNotExist:
            return set()

    def _evaluate_postfix(self, postfix):
        # Вычисляет постфиксное выражение, используя операции над множествами.#
        stack = []
        for token, value in postfix:
            if token == self.TOKEN_TERM:
                stack.append(self._get_doc_set(value))
            elif token == self.TOKEN_NOT:
                if not stack:
                    raise ValueError("NOT без операнда")
                # Все документы, которые есть в системе (хотя бы с одним термом)
                all_docs = set(DocumentTerm.objects.values_list('document_id', flat=True).distinct())
                operand = stack.pop()
                result = all_docs - operand
                stack.append(result)
            elif token == self.TOKEN_AND:
                right = stack.pop()
                left = stack.pop()
                stack.append(left & right)
            elif token == self.TOKEN_OR:
                right = stack.pop()
                left = stack.pop()
                stack.append(left | right)
        if len(stack) != 1:
            raise ValueError("Неверное выражение")
        return stack[0]

    def get_matching_documents(self):
        # Возвращает QuerySet документов, соответствующих запросу
        try:
            postfix = self._to_postfix()
            doc_id_set = self._evaluate_postfix(postfix)
            return Document.objects.filter(id__in=doc_id_set)
        except Exception as e:
            print(f"Ошибка поиска: {e}")
            return Document.objects.none()