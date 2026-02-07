"""
API endpoints для управления чеками
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path
from typing import Optional
from datetime import datetime
import shutil
import re
import logging
import hashlib
from ..database import get_db
from ..models.user import User
from ..models.trip import Trip
from ..models.receipt import Receipt
from ..utils.auth import get_current_active_user
from ..services.qr_reader import QRReader
from ..config import settings

# Удалена функция транслитерации - работаем с именами файлов как есть

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
AMOUNT_MIN = 0.0
AMOUNT_MAX = 200000.0


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class ReceiptUpdate(BaseModel):
    category: Optional[str] = None
    amount: Optional[float] = None
    receipt_date: Optional[datetime] = None
    org_name: Optional[str] = None


@router.post("/trip/{trip_id}/upload")
async def upload_receipt(
    trip_id: int,
    file: UploadFile = File(...),
    category: str = Form("other"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Загрузить чек для командировки
    Автоматически читает QR код и извлекает данные
    """

    # Проверяем существование командировки
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id
    ).first()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )

    # Проверяем формат файла
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    file_extension = Path(file.filename).suffix.lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {', '.join(allowed_extensions)} files are allowed"
        )

    # Читаем файл в память для проверки дублей/размера
    file_bytes = await file.read()
    file_size = len(file_bytes)
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пустой файл. Проверьте загрузку."
        )
    if file_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Слишком большой файл (>{MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."
        )

    incoming_hash = _sha256_bytes(file_bytes)

    # Проверка на дубликаты в рамках командировки
    existing_receipts = db.query(Receipt).filter(Receipt.trip_id == trip_id).all()
    for existing in existing_receipts:
        existing_path = Path(existing.file_path)
        if not existing_path.is_absolute():
            existing_path = settings.BASE_DIR / existing_path
        try:
            if not existing_path.exists():
                continue
            if existing_path.stat().st_size != file_size:
                continue
            if _sha256_file(existing_path) == incoming_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Похоже, этот документ уже был загружен в эту командировку."
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("[UPLOAD] Duplicate check failed for %s: %s", existing_path, e)

    # Создаем папку для чеков - всегда используем абсолютный путь
    receipts_dir = settings.BASE_DIR / settings.UPLOAD_DIR / "receipts" / str(trip_id)
    receipts_dir.mkdir(parents=True, exist_ok=True)

    # Генерируем уникальное имя файла
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{file.filename}"
    file_path = receipts_dir / filename

    # Сохраняем файл
    with open(file_path, "wb") as buffer:
        buffer.write(file_bytes)

    # Читаем QR код
    qr_reader = QRReader()
    debug_log_path = settings.BASE_DIR / "uploads" / "qr_debug.log"
    qr_string, qr_data = qr_reader.process_receipt_file(str(file_path))
    logger.info("[UPLOAD] QR parsed: qr_string=%s qr_data=%s file=%s", bool(qr_string), qr_data, file_path)
    try:
        debug_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(debug_log_path, "a", encoding="utf-8") as debug_log:
            debug_log.write(f"[UPLOAD] file={file_path} qr_string={bool(qr_string)} qr_data={qr_data}\\n")
    except Exception as e:
        logger.error("[UPLOAD] Failed to write debug log: %s", e)

    # Дополнительный fallback: если qr_data не получен, пытаемся распарсить текст/ocr напрямую
    if not qr_data:
        try:
            if file_extension == '.pdf':
                qr_data = qr_reader.parse_text_from_pdf(str(file_path))
                logger.info("[UPLOAD] Fallback parse_text_from_pdf: %s", qr_data)
            elif file_extension in ['.jpg', '.jpeg', '.png', '.bmp']:
                qr_data = qr_reader.parse_text_from_image(str(file_path))
                logger.info("[UPLOAD] Fallback parse_text_from_image: %s", qr_data)
        except Exception as e:
            logger.error("[UPLOAD] Fallback parse failed: %s", e, exc_info=True)
        try:
            with open(debug_log_path, "a", encoding="utf-8") as debug_log:
                debug_log.write(f"[UPLOAD] fallback file={file_path} qr_data={qr_data}\\n")
        except Exception as e:
            logger.error("[UPLOAD] Failed to write fallback debug log: %s", e)

    warnings = []

    # Валидация суммы
    if qr_data and qr_data.get('amount') is not None:
        amount_value = qr_data.get('amount')
        try:
            amount_float = float(amount_value)
            if amount_float < AMOUNT_MIN or amount_float > AMOUNT_MAX:
                warnings.append("amount_out_of_range")
                logger.warning("[UPLOAD] Amount out of range: %s for file %s", amount_float, file_path)
                qr_data['amount'] = None
        except Exception:
            warnings.append("amount_invalid")
            logger.warning("[UPLOAD] Amount invalid: %s for file %s", amount_value, file_path)
            qr_data['amount'] = None

    if not qr_data or qr_data.get('amount') is None:
        warnings.append("amount_missing")
        logger.warning("[UPLOAD] Amount not detected for file %s", file_path)

    # Получаем относительный путь для БД
    relative_path = file_path.relative_to(settings.BASE_DIR)

    # Создаем запись в БД
    receipt = Receipt(
        trip_id=trip_id,
        file_path=str(relative_path).replace('\\', '/'),  # Используем прямые слеши
        file_name=file.filename,
        category=category,
        has_qr=qr_string is not None
    )

    # Если QR прочитан, заполняем данные
    if qr_data:
        receipt.amount = qr_data.get('amount')
        receipt.receipt_date = qr_data.get('date')
        receipt.fn = qr_data.get('fn')
        receipt.fd = qr_data.get('fd')
        receipt.fp = qr_data.get('fp')
        receipt.qr_raw = qr_data.get('raw')
    else:
        logger.warning("[UPLOAD] qr_data is empty for file %s", file_path)

    db.add(receipt)
    db.commit()
    db.refresh(receipt)

    return {
        "id": receipt.id,
        "file_name": receipt.file_name,
        "category": receipt.category,
        "amount": receipt.amount,
        "receipt_date": receipt.receipt_date,
        "has_qr": receipt.has_qr,
        "qr_data": qr_data if qr_data else None,
        "warnings": warnings
    }


@router.put("/{receipt_id}", response_model=dict)
async def update_receipt(
    receipt_id: int,
    receipt_data: ReceiptUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Обновить данные чека (редактирование)"""

    # Получаем чек и проверяем права
    receipt = db.query(Receipt).join(Trip).filter(
        Receipt.id == receipt_id,
        Trip.user_id == current_user.id
    ).first()

    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found"
        )

    # Обновляем поля
    update_data = receipt_data.model_dump(exclude_unset=True)
    if 'amount' in update_data and update_data['amount'] is not None:
        try:
            amount_value = float(update_data['amount'])
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректная сумма"
            )
        if amount_value < AMOUNT_MIN or amount_value > AMOUNT_MAX:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Сумма должна быть от 0 до 200000 рублей"
            )

    for field, value in update_data.items():
        setattr(receipt, field, value)

    # Помечаем как ручной ввод если изменены данные
    if any(field in update_data for field in ['amount', 'receipt_date', 'org_name']):
        receipt.is_manual = True

    db.commit()
    db.refresh(receipt)

    return {
        "id": receipt.id,
        "category": receipt.category,
        "amount": receipt.amount,
        "receipt_date": receipt.receipt_date,
        "org_name": receipt.org_name
    }


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    receipt_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Удалить чек"""

    # Получаем чек и проверяем права
    receipt = db.query(Receipt).join(Trip).filter(
        Receipt.id == receipt_id,
        Trip.user_id == current_user.id
    ).first()

    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found"
        )

    # Удаляем файл
    file_path = Path(receipt.file_path)
    if file_path.exists():
        file_path.unlink()

    # Удаляем запись из БД
    db.delete(receipt)
    db.commit()

    return None
