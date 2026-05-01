import re
import logging
import requests
from .models import Term, DocumentTerm, Document

logger = logging.getLogger(__name__)

class SearchEngine:
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

    # Кэш стемминга на время жизни объекта
    _stem_cache = {}

    def __init__(self, query):
        self.query = query.strip()
        self.tokens = []
        self._tokenize()
        self.is_simple_term = (len(self.tokens) == 1 and self.tokens[0][0] == self.TOKEN_TERM)

    @staticmethod
    def _stem_word(word):
        """Отправляет слово в C++ микросервис на /stem и возвращает основу."""
        word = word.lower()
        if word in SearchEngine._stem_cache:
            return SearchEngine._stem_cache[word]
        try:
            resp = requests.post(
                'http://localhost:8080/stem',
                json={'word': word},
                timeout=2  # быстрый таймаут, чтобы не тормозил поиск
            )
            if resp.status_code == 200:
                stem = resp.json().get('stem', word)
                logger.info('success stemming', word)
                print("Success", stem)
            else:
                stem = word
        except requests.RequestException:
            logger.warning("Не удалось получить стем для '%s', используется оригинал", word)
            stem = word
        SearchEngine._stem_cache[word] = stem
        return stem

    def _tokenize(self):
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
                stemmed = self._stem_word(tok)
                self.tokens.append((self.TOKEN_TERM, stemmed))

    # _to_postfix, _get_doc_set, _evaluate_postfix, get_matching_documents
    # остаются без изменений (как в предыдущей версии с логгированием)
    def _to_postfix(self):
        output = []
        stack = []
        for token, value in self.tokens:
            if token == self.TOKEN_TERM:
                output.append((token, value))
            elif token == self.TOKEN_NOT:
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
        try:
            term_obj = Term.objects.get(term=term)
            doc_ids = DocumentTerm.objects.filter(term=term_obj).values_list('document_id', flat=True)
            return set(doc_ids)
        except Term.DoesNotExist:
            return set()

    def _evaluate_postfix(self, postfix):
        stack = []
        for token, value in postfix:
            if token == self.TOKEN_TERM:
                stack.append(self._get_doc_set(value))
            elif token == self.TOKEN_NOT:
                if not stack:
                    raise ValueError("NOT без операнда")
                all_docs = set(Document.objects.values_list('id', flat=True))
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
        try:
            postfix = self._to_postfix()
            doc_id_set = self._evaluate_postfix(postfix)
            return Document.objects.filter(id__in=doc_id_set)
        except Exception:
            logger.exception("Ошибка поиска по запросу '%s'", self.query)
            return Document.objects.none()