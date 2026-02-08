"""
Сервис для чтения и парсинга QR кодов с чеков
"""
import re
import cv2
from pyzbar import pyzbar
from datetime import datetime
from typing import Optional, Dict, Tuple
from pathlib import Path
import fitz  # PyMuPDF
import numpy as np


class QRReader:
    """Класс для чтения QR кодов с российских фискальных чеков"""

    # Глобальный OCR reader (создается один раз для всех запросов)
    _ocr_reader = None

    # Regex для парсинга QR строки формата: t=YYYYMMDDThhmm&s=SUM&fn=...&i=...&fp=...&n=...
    QR_PATTERN = re.compile(
        r"(?:^|[?&])t=(?P<t>\d{8}T\d{4})"
        r".*?(?:^|[?&])s=(?P<s>\d+(?:\.\d{1,2})?)"
        r".*?(?:^|[?&])fn=(?P<fn>\d+)"
        r".*?(?:^|[?&])i=(?P<i>\d+)"
        r".*?(?:^|[?&])fp=(?P<fp>\d+)"
        r".*?(?:^|[?&])n=(?P<n>\d+)",
        re.IGNORECASE
    )

    @staticmethod
    def _read_image_unicode(image_path: str):
        try:
            path = Path(image_path)
            data = np.fromfile(str(path), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            print(f"[IMG] ERR Failed to read image '{image_path}': {e}")
            return None

    @staticmethod
    def _find_amount_in_text(text: str) -> Optional[float]:
        if not text:
            return None

        normalized_text = re.sub(r'\s+', ' ', text)

        def normalize_ocr_text(value: str) -> str:
            if not value:
                return value
            table = str.maketrans({
                'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н', 'K': 'К',
                'M': 'М', 'O': 'О', 'P': 'Р', 'T': 'Т', 'X': 'Х', 'Y': 'У',
                'a': 'а', 'b': 'в', 'c': 'с', 'e': 'е', 'h': 'н', 'k': 'к',
                'm': 'м', 'o': 'о', 'p': 'р', 't': 'т', 'x': 'х', 'y': 'у',
            })
            return value.translate(table)

        normalized_ocr_text = normalize_ocr_text(normalized_text)

        def parse_amount(amount_str: str) -> Optional[float]:
            if not amount_str:
                return None
            cleaned = amount_str.replace('\xa0', ' ').replace(' ', '').replace(',', '.')
            cleaned = re.sub(r'[^0-9\.]', '', cleaned)
            if not cleaned:
                return None
            try:
                if re.fullmatch(r'\d+', cleaned):
                    return float(int(cleaned))
                return float(cleaned)
            except ValueError:
                return None

        def max_amount_in_window(window: str) -> Optional[float]:
            numbers = re.findall(r'\d[\d\s]*(?:[\.,]\s*\d{2})?', window)
            amounts = [parse_amount(n) for n in numbers]
            amounts = [a for a in amounts if a is not None]
            return max(amounts) if amounts else None

        priority_phrases = [
            'итого по тарифу/сборам',
            'итого',
            'итого/total',
            'total',
        ]

        for phrase in priority_phrases:
            for match in re.finditer(re.escape(phrase), normalized_text, re.IGNORECASE):
                window = normalized_text[match.start():match.start() + 300]
                amount = max_amount_in_window(window)
                if amount is not None:
                    return amount

        fallback_patterns = [
            r'(?:СУММА|Сумма)\s*[:\-]?\s*([^\n]{0,40})',
            r'Стоимость\s+пр\.\s*([^\n]{0,40})',
            r'(?:ОПЛАТА|Оплата)\s*[:\-]?\s*([^\n]{0,40})',
        ]
        for pattern in fallback_patterns:
            match = re.search(pattern, normalized_text, re.IGNORECASE) or re.search(pattern, normalized_ocr_text, re.IGNORECASE)
            if match:
                amount = max_amount_in_window(match.group(1))
                if amount is not None:
                    return amount

        # OCR-ошибки для "СУММА"
        ocr_sum_match = re.search(r'СУММА\s*[:\-]?\s*([^\n]{0,40})', normalized_ocr_text, re.IGNORECASE)
        if ocr_sum_match:
            amount = max_amount_in_window(ocr_sum_match.group(1))
            if amount is not None:
                return amount

        return None

    @staticmethod
    def _init_ocr_reader() -> Optional[object]:
        if QRReader._ocr_reader is not None:
            return QRReader._ocr_reader
        print("[OCR] Initializing EasyOCR reader (first time only)...")
        print("[OCR] Downloading models, please wait (this may take a few minutes)...")
        try:
            import easyocr
        except ImportError:
            print("[OCR] ERR easyocr не установлен. Запустите: pip install easyocr")
            return None
        import sys
        import io
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            QRReader._ocr_reader = easyocr.Reader(['ru', 'en'], gpu=False, verbose=False)
        finally:
            sys.stderr = old_stderr
        print("[OCR] EasyOCR reader initialized")
        return QRReader._ocr_reader

    @staticmethod
    def read_from_image(image_path: str) -> Optional[str]:
        """
        Читает QR код из изображения
        Использует два метода: OpenCV QRCodeDetector и pyzbar
        """
        img = QRReader._read_image_unicode(image_path)
        if img is None:
            return None

        # Метод 1: OpenCV QRCodeDetector
        qr_detector = cv2.QRCodeDetector()
        data, bbox, _ = qr_detector.detectAndDecode(img)

        if data:
            return data

        # Метод 2: pyzbar
        decoded_objects = pyzbar.decode(img)
        for obj in decoded_objects:
            if obj.type == 'QRCODE':
                return obj.data.decode('utf-8', errors='ignore')

        # Метод 3: Улучшение изображения + повторная попытка
        enhanced = QRReader._enhance_image(img)
        decoded_objects = pyzbar.decode(enhanced)
        for obj in decoded_objects:
            if obj.type == 'QRCODE':
                return obj.data.decode('utf-8', errors='ignore')

        return None

    @staticmethod
    def read_from_pdf(pdf_path: str) -> Optional[str]:
        """
        Читает QR код из PDF файла
        Конвертирует страницы в изображения и ищет QR
        """
        try:
            doc = fitz.open(pdf_path)
            print(f"[QR] Открыт PDF: {pdf_path}, страниц: {len(doc)}")

            for page_num in range(len(doc)):
                page = doc[page_num]

                # Увеличиваем DPI для лучшего распознавания (300 DPI вместо стандартных 72)
                zoom = 4  # 72 * 4 = 288 DPI
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                print(f"[QR] Страница {page_num+1}: {pix.width}x{pix.height}, каналов: {pix.n}")

                # Конвертируем в numpy array для OpenCV
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )

                # Конвертируем в BGR если нужно
                if pix.n == 4:  # RGBA
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
                elif pix.n == 3:  # RGB
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                elif pix.n == 1:  # Grayscale
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

                # Создаем grayscale версию для некоторых методов
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

                # Список всех вариантов обработки для проверки
                image_variants = [
                    ("original", img),
                    ("grayscale", gray),
                ]

                # Добавляем бинаризованные версии
                _, binary_thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
                image_variants.append(("binary_thresh", binary_thresh))

                # Адаптивная бинаризация
                adaptive_thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                image_variants.append(("adaptive_thresh", adaptive_thresh))

                # Otsu бинаризация
                _, otsu_thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                image_variants.append(("otsu_thresh", otsu_thresh))

                # Enhanced image
                enhanced = QRReader._enhance_image(img)
                image_variants.append(("enhanced", enhanced))

                # Попробуем все варианты
                qr_detector = cv2.QRCodeDetector()

                for variant_name, variant_img in image_variants:
                    # Метод 1: OpenCV QRCodeDetector
                    data, bbox, _ = qr_detector.detectAndDecode(variant_img)
                    if data:
                        print(f"[QR] OK Найден QR код (OpenCV-{variant_name}): {data[:50]}...")
                        doc.close()
                        return data

                    # Метод 2: pyzbar
                    decoded_objects = pyzbar.decode(variant_img)
                    for obj in decoded_objects:
                        if obj.type == 'QRCODE':
                            qr_data = obj.data.decode('utf-8', errors='ignore')
                            print(f"[QR] OK Найден QR код (pyzbar-{variant_name}): {qr_data[:50]}...")
                            doc.close()
                            return qr_data

                print(f"[QR] Страница {page_num+1}: QR не найден после {len(image_variants)} вариантов обработки")

            doc.close()
            print("[QR] ERR QR код не найден ни на одной странице")
        except Exception as e:
            print(f"[QR] ERR Ошибка при чтении PDF: {e}")
            import traceback
            traceback.print_exc()

        return None

    @staticmethod
    def parse_qr_string(qr_string: str) -> Optional[Dict]:
        """
        Парсит QR строку российского фискального чека
        Возвращает: {date, amount, fn, fd, fp, n, raw}
        """
        if not qr_string:
            return None

        match = QRReader.QR_PATTERN.search(qr_string)
        if not match:
            return None

        try:
            dt = datetime.strptime(match.group('t'), '%Y%m%dT%H%M')
            amount = float(match.group('s'))

            return {
                'date': dt,
                'amount': amount,
                'fn': match.group('fn'),
                'fd': match.group('i'),
                'fp': match.group('fp'),
                'n': match.group('n'),
                'raw': qr_string
            }
        except Exception as e:
            print(f"Ошибка парсинга QR: {e}")
            return None

    @staticmethod
    def parse_text_from_pdf(pdf_path: str) -> Optional[Dict]:
        """
        Парсит текст из PDF чека когда QR код не найден
        Ищет дату, сумму, ФН, ФД в тексте
        """
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()

            print(f"[TEXT] Extracted {len(text)} chars from PDF")

            def run_ocr_extract() -> str:
                reader = QRReader._init_ocr_reader()
                if reader is None:
                    return ""

                # Конвертируем PDF в изображение
                page = doc[0]
                zoom = 3  # 216 DPI
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Конвертируем в numpy array
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )

                # Конвертируем в RGB если нужно
                if pix.n == 4:  # RGBA
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                elif pix.n == 1:  # Grayscale
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
                # pix.n == 3 - уже RGB

                print(f"[OCR] Processing image {img.shape}...")

                # Распознаем текст
                result = reader.readtext(img)

                # Собираем распознанный текст
                ocr_text = " ".join([item[1] for item in result])
                print(f"[OCR] Extracted {len(ocr_text)} chars: {ocr_text[:100]}...")
                return ocr_text

            # Если текст не извлечен - используем OCR
            if len(text.strip()) == 0:
                print("[TEXT] No text in PDF, using OCR to extract text from image")
                text = run_ocr_extract()

            doc.close()

            # Ищем дату в формате DD.MM.YYYY HH:MM или DD.MM.YYYY, HH:MM
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})[,\s]+(\d{2}:\d{2})', text)
            if date_match:
                date_str = f"{date_match.group(1)} {date_match.group(2)}"
                receipt_date = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
                print(f"[TEXT] Found date: {receipt_date}")
            else:
                print("[TEXT] Date not found in text")
                receipt_date = None

            amount = QRReader._find_amount_in_text(text)
            if amount is not None:
                print(f"[TEXT] Found amount: {amount}")

            if not amount:
                print("[TEXT] Amount not found in text")
                if len(text.strip()) > 0:
                    print("[TEXT] Trying OCR to find amount")
                ocr_text = run_ocr_extract()
                if ocr_text:
                    text = f"{text} {ocr_text}"
                    amount = QRReader._find_amount_in_text(text)
                    if amount is not None:
                        print(f"[TEXT] Found amount after OCR: {amount}")

            # Ищем ФН, ФД, ФП
            fn_match = re.search(r'(?:ФН|N ФН)[:№\s]+(\d+)', text)
            fd_match = re.search(r'(?:ФД|N ФД)[:№\s]+(\d+)', text)
            fp_match = re.search(r'(?:ФП|N ФП)[:№\s]+(\d+)', text)

            fn = fn_match.group(1) if fn_match else None
            fd = fd_match.group(1) if fd_match else None
            fp = fp_match.group(1) if fp_match else None

            if fn:
                print(f"[TEXT] Found FN: {fn}")
            if fd:
                print(f"[TEXT] Found FD: {fd}")
            if fp:
                print(f"[TEXT] Found FP: {fp}")

            # Если нашли хотя бы дату или сумму, возвращаем результат
            if receipt_date or amount:
                return {
                    'date': receipt_date,
                    'amount': amount,
                    'fn': fn,
                    'fd': fd,
                    'fp': fp,
                    'raw': f"t={receipt_date.strftime('%Y%m%dT%H%M') if receipt_date else ''}&&s={amount}&fn={fn}&i={fd}&fp={fp}" if fn else None
                }

            return None

        except Exception as e:
            print(f"[TEXT] Error parsing text from PDF: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def parse_text_from_image(image_path: str) -> Optional[Dict]:
        """
        Парсит текст из изображения чека/билета когда QR код не найден
        Ищет дату и сумму через OCR
        """
        try:
            img = QRReader._read_image_unicode(image_path)
            if img is None:
                return None

            reader = QRReader._init_ocr_reader()
            if reader is None:
                return None

            # BGR -> RGB
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            print(f"[OCR] Processing image {rgb.shape}...")
            result = reader.readtext(rgb)
            text = " ".join([item[1] for item in result])
            print(f"[OCR] Extracted {len(text)} chars: {text[:100]}...")

            # Дата в формате DD.MM.YYYY HH:MM
            date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})[,\s]+(\d{2}:\d{2})', text)
            if date_match:
                date_str = f"{date_match.group(1)} {date_match.group(2)}"
                receipt_date = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
                print(f"[TEXT] Found date: {receipt_date}")
            else:
                receipt_date = None

            amount = QRReader._find_amount_in_text(text)
            if amount is not None:
                print(f"[TEXT] Found amount: {amount}")

            if receipt_date or amount:
                return {
                    'date': receipt_date,
                    'amount': amount,
                    'fn': None,
                    'fd': None,
                    'fp': None,
                    'raw': None
                }

            return None
        except Exception as e:
            print(f"[TEXT] Error parsing text from image: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def process_receipt_file(file_path: str) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Обрабатывает файл чека (jpg/png/pdf)
        Возвращает: (qr_string, parsed_data)
        """
        path = Path(file_path)
        extension = path.suffix.lower()

        qr_string = None

        if extension == '.pdf':
            qr_string = QRReader.read_from_pdf(file_path)

            # Если QR не найден, пробуем парсить текст
            if not qr_string:
                print("[QR] QR not found, trying to parse text from PDF")
                parsed_data = QRReader.parse_text_from_pdf(file_path)
                if parsed_data:
                    return None, parsed_data
            else:
                # QR найден, но может быть не фискальный - пробуем распарсить текст
                parsed_data = QRReader.parse_qr_string(qr_string)
                if not parsed_data:
                    print("[QR] QR found but not fiscal, trying to parse text from PDF")
                    parsed_data = QRReader.parse_text_from_pdf(file_path)
                    if parsed_data:
                        return qr_string, parsed_data

        elif extension in ['.jpg', '.jpeg', '.png', '.bmp']:
            qr_string = QRReader.read_from_image(file_path)
            if not qr_string:
                print("[QR] QR not found in image, trying OCR to parse text")
                parsed_data = QRReader.parse_text_from_image(file_path)
                if parsed_data:
                    return None, parsed_data
            else:
                parsed_data = QRReader.parse_qr_string(qr_string)
                if not parsed_data:
                    print("[QR] QR found but not fiscal, trying OCR to parse text")
                    parsed_data = QRReader.parse_text_from_image(file_path)
                    if parsed_data:
                        return qr_string, parsed_data
        else:
            return None, None

        if qr_string:
            parsed_data = QRReader.parse_qr_string(qr_string)
            return qr_string, parsed_data

        return None, None

    @staticmethod
    def _enhance_image(img):
        """
        Улучшает изображение для лучшего распознавания QR
        """
        # Конвертация в grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Увеличение контраста (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Бинаризация
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary
