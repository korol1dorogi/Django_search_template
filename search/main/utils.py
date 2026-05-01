import os
import re
import logging
import docx
import PyPDF2
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()

    # .txt и .md
    if ext in ('.txt', '.md'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    return f.read()
            except Exception:
                logger.exception("Ошибка при чтении текстового файла %s", file_path)
                return ''
        except Exception:
            logger.exception("Ошибка при открытии файла %s", file_path)
            return ''

    # .docx
    elif ext == '.docx':
        try:
            doc = docx.Document(file_path)
            return '\n'.join([para.text for para in doc.paragraphs])
        except Exception:
            logger.exception("Ошибка при обработке DOCX: %s", file_path)
            return ''

    # .pdf
    elif ext == '.pdf':
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ''
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text
                return text
        except Exception:
            logger.exception("Ошибка при обработке PDF: %s", file_path)
            return ''

    # .fb2
    elif ext == '.fb2':
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            ns = {'fb': 'http://www.gribuser.ru/xml/fictionbook/2.0'}
            texts = []
            for elem in root.findall('.//fb:p', ns):
                if elem.text:
                    texts.append(elem.text)
            return '\n'.join(texts)
        except Exception:
            logger.exception("Ошибка при обработке FB2: %s", file_path)
            return ''

    # .epub
    elif ext == '.epub':
        try:
            from ebooklib import epub
            try:
                from ebooklib import ITEM_DOCUMENT
            except ImportError:
                ITEM_DOCUMENT = 9  # тип документа по умолчанию

            book = epub.read_epub(file_path)
            text = ''
            for item in book.get_items():
                if item.get_type() == ITEM_DOCUMENT:
                    content = item.get_body_content().decode('utf-8')
                    text += re.sub(r'<[^>]+>', ' ', content)
            return text
        except Exception:
            logger.exception("Ошибка при обработке EPUB: %s", file_path)
            return ''

    else:
        logger.warning("Неподдерживаемое расширение файла: %s", file_path)
        return ''