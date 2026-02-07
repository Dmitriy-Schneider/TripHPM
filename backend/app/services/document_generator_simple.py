"""
Упрощенный генератор документов - работает только с готовыми шаблонами
Простая логика: копирование шаблона + заполнение ячеек + архивирование
"""
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Dict, Iterable
from decimal import Decimal, ROUND_CEILING
import re
import zipfile
import shutil

from docx import Document
from openpyxl import load_workbook
from num2words import num2words
import logging


class SimpleDocumentGenerator:
    """Упрощенный генератор документов"""

    def __init__(self, templates_dir: Path, output_dir: Path):
        self.templates_dir = Path(templates_dir)
        self.output_dir = Path(output_dir)

    def generate_all(self, trip_data: Dict) -> Dict[str, str]:
        """Генерирует все документы - простая логика"""

        # Создаем папку для командировки
        folder_name = f"{trip_data['date_from'].strftime('%Y-%m-%d')}_{trip_data['destination_city']}_{trip_data['fio'].split()[0]}"
        trip_folder = self.output_dir / folder_name

        # Удаляем старую папку если есть
        if trip_folder.exists():
            shutil.rmtree(trip_folder)

        # Создаем структуру папок
        trip_folder.mkdir(parents=True)
        (trip_folder / "documents").mkdir()
        (trip_folder / "receipts").mkdir()

        results = {}

        # 1. Приказ
        results['prikaz'] = self._generate_prikaz(trip_data, trip_folder)

        # 2. Авансовый отчет
        results['ao'] = self._generate_ao(trip_data, trip_folder)

        # 3. Служебная записка
        results['sz'] = self._generate_sz(trip_data, trip_folder)

        # 4. Копируем чеки
        self._copy_receipts(trip_data, trip_folder)

        # 5. Создаем ZIP
        results['zip'] = self._create_zip(trip_folder)

        return results

    def _generate_prikaz(self, trip_data: Dict, output_folder: Path) -> str:
        """Генерирует Приказ - заполняет таблицы и нужные поля в шаблоне"""
        template_path = self.templates_dir / "prikaz_template.docx"
        output_path = output_folder / "documents" / "Приказ.docx"

        doc = Document(template_path)

        org_name = trip_data.get('org_name', 'ООО «ВЭМ»')
        fio = trip_data['fio']
        tab_no = trip_data.get('tab_no', '')
        department = trip_data.get('department', '')
        position = trip_data.get('position', '')
        destination_org = trip_data['destination_org']
        purpose = trip_data['purpose']
        days = str(trip_data['days'])
        date_from = trip_data['date_from']
        date_to = trip_data['date_to']
        order_date = self._calculate_doc_date(date_from)

        tables = doc.tables
        if len(tables) >= 8:
            # Организация
            tables[0].cell(2, 0).text = org_name
            tables[0].cell(2, 1).text = org_name
            # Дата составления
            tables[1].cell(1, 2).text = order_date.strftime('%d.%m.%Y')
            # ФИО и табельный
            tables[2].cell(1, 0).text = fio
            tables[2].cell(1, 1).text = tab_no
            # Место назначения
            tables[3].cell(0, 0).text = destination_org
            # Количество дней
            tables[4].cell(0, 1).text = days
            # Даты командировки
            self._fill_split_date(tables[5], date_from, date_to)
            # Цель
            tables[6].cell(0, 1).text = purpose
            # Источник финансирования
            tables[7].cell(0, 1).text = org_name
            # Дата ознакомления работника
            if len(tables) >= 10:
                self._fill_ack_date(tables[9], order_date)

        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if department and text == "Администрация":
                paragraph.text = department
            elif position and text == "Торговый представитель":
                paragraph.text = position

        doc.save(output_path)
        return str(output_path)

    def _generate_ao(self, trip_data: Dict, output_folder: Path) -> str:
        """Генерирует Авансовый отчет - прямая запись в ячейки"""
        template_path = self.templates_dir / "ao_template.xlsx"
        output_path = output_folder / "documents" / "Авансовый_отчет.xlsx"

        try:
            from win32com import client as win32  # type: ignore
        except Exception:
            win32 = None

        if win32:
            return self._generate_ao_com(
                win32,
                template_path,
                output_path,
                trip_data
            )

        logger = logging.getLogger(__name__)
        logger.warning("win32com is not available, falling back to openpyxl for AO generation.")

        # Открываем шаблон
        wb = load_workbook(template_path, keep_vba=True, data_only=False, keep_links=True)
        ws = wb.active

        # Дата оформления документа (ячейка Z13)
        doc_date = trip_data.get('document_date') or trip_data.get('date_to') or trip_data.get('date_from')
        if isinstance(doc_date, datetime):
            doc_date = doc_date.date()
        if isinstance(doc_date, date):
            ws["Z13"].value = doc_date.strftime('%d.%m.%y')

        # Маппинг категорий
        category_names = {
            'taxi': 'Такси',
            'fuel': 'Топливо',
            'hotel': 'Гостиница',
            'restaurant': 'Автобус',
            'bus': 'Автобус',
            'flight': 'Самолет',
            'airplane': 'Самолет',
            'train': 'Поезд',
            'самолет': 'Самолет',
            'поезд': 'Поезд',
            'автобус': 'Автобус',
            'other': 'Представительские'
        }

        category_order = ['fuel', 'taxi', 'flight', 'airplane', 'train', 'bus', 'hotel', 'restaurant', 'other']

        # Прямая запись в ячейки - строка 63 первая строка таблицы
        # Колонка P (16) - название, колонка Y (25) - сумма
        raw_expenses = trip_data.get('expenses_by_category', {})
        expenses = {}
        for key, amount in raw_expenses.items():
            normalized_key = self._normalize_category_key(key)
            expenses[normalized_key] = (expenses.get(normalized_key, 0) or 0) + (amount or 0)
        row = 63

        # Очищаем диапазон расходов, чтобы не осталось шаблонных значений
        for clear_row in range(63, 85):
            ws.cell(clear_row, 16).value = None
            ws.cell(clear_row, 25).value = None

        # Заполняем расходы
        for category in self._ordered_categories(expenses.keys(), category_order):
            amount = expenses.get(category)
            if amount and amount > 0:
                normalized_category = self._normalize_category_key(category)
                display_category = category_names.get(normalized_category, category)
                ws.cell(row, 16).value = display_category  # Колонка P
                ws.cell(row, 25).value = self._to_money(amount)  # Колонка Y
                row += 1

        # Суточные
        per_diem = trip_data.get('per_diem_to_pay', 0)
        if per_diem > 0:
            ws.cell(row, 16).value = 'Суточные'
            ws.cell(row, 25).value = self._to_money(per_diem)

        wb.save(output_path)
        return str(output_path)

    def _generate_ao_com(self, win32, template_path: Path, output_path: Path, trip_data: Dict) -> str:
        """Генерирует Авансовый отчет через Excel COM (максимальная совместимость)."""
        shutil.copy(template_path, output_path)

        excel = win32.Dispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = None
        try:
            wb = excel.Workbooks.Open(str(output_path.resolve()))
            ws = wb.Worksheets(1)

            doc_date = trip_data.get('document_date') or datetime.today().date()
            if isinstance(doc_date, datetime):
                doc_date = doc_date.date()
            if isinstance(doc_date, date):
                ws.Range("Z13").Value = doc_date.strftime('%d.%m.%y')

            category_names = {
                'taxi': 'Такси',
                'fuel': 'Топливо',
                'hotel': 'Гостиница',
                'restaurant': 'Автобус',
                'bus': 'Автобус',
                'flight': 'Самолет',
                'airplane': 'Самолет',
                'train': 'Поезд',
                'самолет': 'Самолет',
                'поезд': 'Поезд',
                'автобус': 'Автобус',
                'other': 'Представительские'
            }
            category_order = ['fuel', 'taxi', 'flight', 'airplane', 'train', 'bus', 'hotel', 'restaurant', 'other']

            for clear_row in range(63, 85):
                ws.Range(f"P{clear_row}").Value = ""
                ws.Range(f"Y{clear_row}").Value = ""

            row = 63
            raw_expenses = trip_data.get('expenses_by_category', {})
            expenses = {}
            for key, amount in raw_expenses.items():
                normalized_key = self._normalize_category_key(key)
                expenses[normalized_key] = (expenses.get(normalized_key, 0) or 0) + (amount or 0)
            for category in self._ordered_categories(expenses.keys(), category_order):
                amount = expenses.get(category)
                if amount and amount > 0:
                    normalized_category = self._normalize_category_key(category)
                    display_category = category_names.get(normalized_category, category)
                    ws.Range(f"P{row}").Value = display_category
                    ws.Range(f"Y{row}").Value = float(self._to_money(amount))
                    row += 1

            per_diem = trip_data.get('per_diem_to_pay', 0)
            if per_diem > 0:
                ws.Range(f"P{row}").Value = "Суточные"
                ws.Range(f"Y{row}").Value = float(self._to_money(per_diem))

            wb.Save()
            return str(output_path)
        finally:
            if wb is not None:
                wb.Close(False)
            excel.Quit()
            try:
                import gc
                gc.collect()
            except Exception:
                pass

    def _generate_sz(self, trip_data: Dict, output_folder: Path) -> str:
        """Генерирует Служебную записку"""
        template_path = self.templates_dir / "sz_template.docx"
        output_path = output_folder / "documents" / "Служебная_записка.docx"

        logger = logging.getLogger(__name__)
        doc = Document(template_path)

        org_name = trip_data.get('org_name', 'ООО «ВЭМ»')
        fio = trip_data['fio']
        fio_short = self._fio_short(fio)
        doc_date = self._calculate_doc_date(trip_data['date_from'])

        total_expenses = trip_data.get('total_expenses', 0)
        total_expenses_rounded = self._ceil_rubles(total_expenses)
        total_expenses_words = num2words(total_expenses_rounded, lang='ru')
        logger.info(
            "[SZ] total_expenses=%s rounded=%s words='%s' doc_date=%s template=%s output=%s",
            total_expenses,
            total_expenses_rounded,
            total_expenses_words,
            doc_date.strftime('%d.%m.%Y'),
            template_path,
            output_path
        )

        sum_pattern = re.compile(r'сумму\s+\d+[\d\s]*\s*\([^)]*\)\s+рублей', re.IGNORECASE)
        date_pattern = re.compile(r'\d{2}\.\d{2}\.\d{4}')

        replaced_sum = 0
        replaced_date = 0
        for paragraph in doc.paragraphs:
            raw_text = paragraph.text
            text = raw_text.strip()

            if text == "ООО «ВЭМ»":
                paragraph.text = org_name
                continue

            if text.startswith("от "):
                paragraph.text = f"от {fio_short}"
                continue

            updated = sum_pattern.sub(
                f"сумму {total_expenses_rounded} ({total_expenses_words}) рублей",
                raw_text
            )
            updated = date_pattern.sub(doc_date.strftime('%d.%m.%Y'), updated)

            if updated != raw_text:
                if "сумму" in raw_text and "рублей" in raw_text:
                    replaced_sum += 1
                    logger.info("[SZ] Replaced sum line: '%s' -> '%s'", raw_text, updated)
                if raw_text.strip().startswith("Дата"):
                    replaced_date += 1
                    logger.info("[SZ] Replaced date line: '%s' -> '%s'", raw_text, updated)
                paragraph.text = updated

        logger.info("[SZ] replacements: sum=%s date=%s", replaced_sum, replaced_date)

        doc.save(output_path)
        return str(output_path)

    @staticmethod
    def _ordered_categories(categories: Iterable[str], order: Iterable[str]) -> Iterable[str]:
        seen = set()
        ordered = []
        for key in order:
            if key in categories:
                ordered.append(key)
                seen.add(key)
        for key in categories:
            if key not in seen:
                ordered.append(key)
        return ordered

    @staticmethod
    def _normalize_category_key(category: str) -> str:
        if category is None:
            return 'other'
        raw = str(category).strip()
        lower = raw.lower()
        mapping = {
            'самолет': 'airplane',
            'airplane': 'airplane',
            'flight': 'airplane',
            'поезд': 'train',
            'train': 'train',
            'такси': 'taxi',
            'taxi': 'taxi',
            'топливо': 'fuel',
            'fuel': 'fuel',
            'гостиница': 'hotel',
            'hotel': 'hotel',
            'автобус': 'bus',
            'bus': 'bus',
            'ресторан': 'bus',
            'restaurant': 'bus',
            'представительские': 'other',
            'other': 'other',
        }
        return mapping.get(lower, raw)

    @staticmethod
    def _to_money(value: float) -> float:
        return float(Decimal(str(value)).quantize(Decimal("0.01")))

    @staticmethod
    def _ceil_rubles(value: float) -> int:
        return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_CEILING))

    @staticmethod
    def _calculate_doc_date(date_from: date) -> date:
        doc_date = date_from - timedelta(days=2)
        while doc_date.weekday() >= 5:
            doc_date -= timedelta(days=1)
        return doc_date

    @staticmethod
    def _fio_short(fio: str) -> str:
        parts = fio.strip().split()
        if not parts:
            return fio
        surname = parts[0]
        initials = "".join([f"{p[0]}." for p in parts[1:3] if p])
        return f"{surname} {initials}".strip()

    @staticmethod
    def _fill_split_date(table, date_from: date, date_to: date):
        year_from = date_from.strftime('%Y')
        year_to = date_to.strftime('%Y')
        table.cell(0, 2).text = date_from.strftime('%d')
        table.cell(0, 4).text = date_from.strftime('%m')
        table.cell(0, 5).text = year_from[:2]
        table.cell(0, 6).text = year_from[2:]
        table.cell(0, 8).text = date_to.strftime('%d')
        table.cell(0, 10).text = date_to.strftime('%m')
        table.cell(0, 11).text = year_to[:2]
        table.cell(0, 12).text = year_to[2:]

    @staticmethod
    def _fill_ack_date(table, ack_date: date):
        year = ack_date.strftime('%Y')
        table.cell(0, 3).text = ack_date.strftime('%d')
        table.cell(0, 5).text = ack_date.strftime('%m')
        table.cell(0, 6).text = year[:2]
        table.cell(0, 7).text = year[2:]

    def _copy_receipts(self, trip_data: Dict, output_folder: Path):
        """Копирует чеки"""
        receipts_folder = output_folder / "receipts"
        receipts = trip_data.get('receipts', [])

        for receipt in receipts:
            if 'file_path' not in receipt:
                continue

            source = Path(receipt['file_path'])

            # Если путь относительный - делаем абсолютным
            if not source.is_absolute():
                from ..config import settings
                source = settings.BASE_DIR / source

            if source.exists():
                dest = receipts_folder / f"{receipt.get('category', 'other')}_{source.name}"
                shutil.copy(source, dest)

    def _create_zip(self, trip_folder: Path) -> str:
        """Создает ZIP архив"""
        zip_path = trip_folder.parent / f"{trip_folder.name}.zip"

        # Удаляем старый ZIP
        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in trip_folder.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(trip_folder.parent)
                    zipf.write(file_path, arcname)

        return str(zip_path)


def calculate_per_diem_days(date_from, date_to, departure_time, arrival_time) -> float:
    """Расчет суточных с коэффициентами"""

    # Коэффициент выезда
    if departure_time:
        if departure_time.hour < 12:
            departure_coef = 1.0
        elif 12 <= departure_time.hour < 18:
            departure_coef = 0.5
        else:
            departure_coef = 0.4
    else:
        departure_coef = 1.0

    # Коэффициент приезда
    if arrival_time:
        if arrival_time.hour >= 18:
            arrival_coef = 1.0
        elif 12 <= arrival_time.hour < 18:
            arrival_coef = 0.5
        else:
            arrival_coef = 0.4
    else:
        arrival_coef = 1.0

    # Полные дни
    days_diff = (date_to - date_from).days
    full_days = max(0, days_diff - 1)

    total_days = departure_coef + full_days + arrival_coef

    return total_days
