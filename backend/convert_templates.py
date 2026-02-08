"""
Скрипт для автоматической конвертации шаблонов
.doc → .docx
.xls → .xlsx
"""
import shutil
from pathlib import Path
import sys


def convert_doc_to_docx(doc_path: Path, output_dir: Path):
    """Конвертация .doc → .docx через python-docx"""
    try:
        from docx import Document

        print(f"Конвертация {doc_path.name}...")

        # Открываем и сохраняем как .docx
        doc = Document(doc_path)
        output_path = output_dir / doc_path.with_suffix('.docx').name
        doc.save(output_path)

        print(f"  ✓ Сохранено: {output_path.name}")
        return True

    except Exception as e:
        print(f"  ✗ Ошибка: {e}")
        print(f"  Попробуйте конвертировать вручную через Word/LibreOffice")
        return False


def convert_xls_to_xlsx(xls_path: Path, output_dir: Path):
    """Конвертация .xls → .xlsx через pandas + openpyxl"""
    try:
        import pandas as pd
        from openpyxl import Workbook
        import xlrd

        print(f"Конвертация {xls_path.name}...")

        # Читаем старый формат
        xls = pd.ExcelFile(xls_path, engine='xlrd')

        # Создаем новый файл
        output_path = output_dir / xls_path.with_suffix('.xlsx').name

        # Копируем все листы
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)

        print(f"  ✓ Сохранено: {output_path.name}")
        return True

    except Exception as e:
        print(f"  ✗ Ошибка: {e}")
        print(f"  Попробуйте конвертировать вручную через Excel/LibreOffice")
        return False


def main():
    """Главная функция"""
    print("="*60)
    print("КОНВЕРТАЦИЯ ШАБЛОНОВ")
    print("="*60)

    # Определяем пути
    base_dir = Path(__file__).parent.parent
    source_dir = base_dir
    output_dir = Path(__file__).parent / "templates"

    # Создаем папку templates если нет
    output_dir.mkdir(exist_ok=True)

    print(f"\nИщем файлы в: {source_dir}")
    print(f"Результаты в: {output_dir}\n")

    # Находим файлы для конвертации
    doc_files = list(source_dir.glob("*.doc"))
    xls_files = list(source_dir.glob("*.xls"))

    if not doc_files and not xls_files:
        print("⚠️  Файлы .doc и .xls не найдены")
        print("\nПоместите следующие файлы в корневую папку проекта:")
        print("  - СЗ *.doc")
        print("  - АО *.xls")
        print("  - Суточные *.xls")
        return

    success_count = 0
    total_count = len(doc_files) + len(xls_files)

    # Конвертируем .doc файлы
    if doc_files:
        print("\n--- Конвертация Word документов ---\n")
        for doc_file in doc_files:
            if convert_doc_to_docx(doc_file, output_dir):
                success_count += 1

    # Конвертируем .xls файлы
    if xls_files:
        print("\n--- Конвертация Excel документов ---\n")
        for xls_file in xls_files:
            if convert_xls_to_xlsx(xls_file, output_dir):
                success_count += 1

    # Копируем уже конвертированные файлы
    docx_files = list(source_dir.glob("Приказ*.docx"))
    for docx_file in docx_files:
        dest = output_dir / docx_file.name
        shutil.copy(docx_file, dest)
        print(f"Скопирован: {docx_file.name}")
        success_count += 1
        total_count += 1

    print("\n" + "="*60)
    print(f"ГОТОВО: {success_count}/{total_count} файлов сконвертировано")
    print("="*60)

    # Проверяем результат
    print("\nФайлы в templates/:")
    for file in sorted(output_dir.glob("*")):
        print(f"  ✓ {file.name}")

    print("\n📝 СЛЕДУЮЩИЙ ШАГ:")
    print("\nПереименуйте файлы в стандартные имена:")
    print("  1. Приказ*.docx → prikaz_template.docx")
    print("  2. СЗ*.docx → sz_template.docx")
    print("  3. АО*.xlsx → ao_template.xlsx")
    print("  4. Суточные*.xlsx → sutochnye_template.xlsx")
    print("\nЗатем добавьте placeholders согласно docs/TEMPLATES_SETUP.md")


if __name__ == "__main__":
    main()
