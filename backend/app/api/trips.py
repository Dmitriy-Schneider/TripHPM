"""
API endpoints для управления командировками
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date, time, datetime
from typing import List, Optional
from pathlib import Path
import logging
from ..database import get_db
from ..models.user import User
from ..models.trip import Trip
from ..models.receipt import Receipt
from ..utils.auth import get_current_active_user
from ..services.document_generator_simple import SimpleDocumentGenerator, calculate_per_diem_days
from ..services.qr_reader import QRReader
from ..config import settings

router = APIRouter()

logger = logging.getLogger(__name__)


def _fill_missing_receipt_data(receipts: List[Receipt], db: Session) -> None:
    """Попытаться заполнить недостающие суммы/даты по файлам (lazy-обработка)."""
    if not receipts:
        return

    qr_reader = QRReader()
    updated = False

    for receipt in receipts:
        if receipt.is_manual:
            continue

        if receipt.amount not in (None, 0):
            continue

        file_path = Path(receipt.file_path)
        if not file_path.is_absolute():
            file_path = settings.BASE_DIR / file_path

        if not file_path.exists():
            logger.warning("[PARSE] File not found for receipt %s: %s", receipt.id, file_path)
            continue

        try:
            qr_string, qr_data = qr_reader.process_receipt_file(str(file_path))
        except Exception as e:
            logger.error("[PARSE] Failed to parse receipt %s: %s", receipt.id, e, exc_info=True)
            continue

        if not qr_data:
            continue

        amount = qr_data.get('amount')
        if amount is not None:
            receipt.amount = amount
        if receipt.receipt_date is None and qr_data.get('date'):
            receipt.receipt_date = qr_data.get('date')

        if qr_data.get('fn'):
            receipt.fn = qr_data.get('fn')
        if qr_data.get('fd'):
            receipt.fd = qr_data.get('fd')
        if qr_data.get('fp'):
            receipt.fp = qr_data.get('fp')
        if qr_data.get('raw'):
            receipt.qr_raw = qr_data.get('raw')

        if qr_string:
            receipt.has_qr = True

        updated = True

    if updated:
        db.commit()
        for receipt in receipts:
            db.refresh(receipt)


class TripCreate(BaseModel):
    destination_city: str
    destination_org: str
    date_from: date
    date_to: date
    departure_time: Optional[time] = None
    arrival_time: Optional[time] = None
    purpose: str
    meals_breakfast_count: int = 0
    meals_lunch_count: int = 0
    meals_dinner_count: int = 0
    advance_rub: float = 0.0


class TripUpdate(BaseModel):
    destination_city: Optional[str] = None
    destination_org: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    departure_time: Optional[time] = None
    arrival_time: Optional[time] = None
    purpose: Optional[str] = None
    meals_breakfast_count: Optional[int] = None
    meals_lunch_count: Optional[int] = None
    meals_dinner_count: Optional[int] = None
    advance_rub: Optional[float] = None
    status: Optional[str] = None


class ReceiptInfo(BaseModel):
    id: int
    category: str
    amount: Optional[float]
    receipt_date: Optional[datetime]
    org_name: Optional[str]
    file_name: str
    has_qr: bool

    class Config:
        from_attributes = True


class TripResponse(BaseModel):
    id: int
    destination_city: str
    destination_org: str
    date_from: date
    date_to: date
    departure_time: Optional[time]
    arrival_time: Optional[time]
    purpose: str
    meals_breakfast_count: int
    meals_lunch_count: int
    meals_dinner_count: int
    advance_rub: float
    status: str
    created_at: datetime
    receipts: List[ReceiptInfo] = []

    class Config:
        from_attributes = True


@router.post("/", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    trip_data: TripCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Создать новую командировку"""

    new_trip = Trip(
        user_id=current_user.id,
        **trip_data.model_dump()
    )

    db.add(new_trip)
    db.commit()
    db.refresh(new_trip)

    return new_trip


@router.get("/", response_model=List[TripResponse])
async def get_trips(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Получить список командировок текущего пользователя"""

    trips = db.query(Trip).filter(
        Trip.user_id == current_user.id
    ).offset(skip).limit(limit).all()

    return trips


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Получить командировку по ID"""

    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id
    ).first()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )

    # Lazy-обработка: если суммы не распознаны при загрузке, попробуем сейчас
    _fill_missing_receipt_data(trip.receipts, db)

    return trip


@router.put("/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: int,
    trip_data: TripUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Обновить командировку"""

    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id
    ).first()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )

    # Обновляем поля
    update_data = trip_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(trip, field, value)

    db.commit()
    db.refresh(trip)

    return trip


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(
    trip_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Удалить командировку"""
    import shutil

    logger.info(f"[DELETE] Starting deletion for trip_id={trip_id}, user={current_user.username}")

    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id
    ).first()

    if not trip:
        logger.error(f"[DELETE] Trip {trip_id} not found for user {current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )

    # Удаляем папку с чеками
    receipts_dir = settings.UPLOAD_DIR / "receipts" / str(trip_id)
    if receipts_dir.exists():
        logger.info(f"[DELETE] Removing receipts directory: {receipts_dir}")
        shutil.rmtree(receipts_dir)
    else:
        logger.debug(f"[DELETE] Receipts directory not found: {receipts_dir}")

    # Удаляем папку с документами
    folder_name = f"{trip.date_from.strftime('%Y-%m-%d')}_{trip.destination_city}_{current_user.fio.split()[0]}"
    output_dir = settings.OUTPUT_DIR / folder_name
    if output_dir.exists():
        logger.info(f"[DELETE] Removing output directory: {output_dir}")
        shutil.rmtree(output_dir)
    else:
        logger.debug(f"[DELETE] Output directory not found: {output_dir}")

    # Удаляем ZIP архив
    zip_path = settings.OUTPUT_DIR / f"{folder_name}.zip"
    if zip_path.exists():
        logger.info(f"[DELETE] Removing ZIP archive: {zip_path}")
        zip_path.unlink()
    else:
        logger.debug(f"[DELETE] ZIP archive not found: {zip_path}")

    # Удаляем запись из БД (каскадно удалятся чеки)
    db.delete(trip)
    db.commit()

    logger.info(f"[DELETE] Trip {trip_id} successfully deleted")
    return None


@router.get("/{trip_id}/preview")
async def preview_generation(
    trip_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Предпросмотр данных перед генерацией документов"""

    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id
    ).first()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )

    # Lazy-обработка: добираем суммы/даты из файлов, если еще не распознаны
    _fill_missing_receipt_data(trip.receipts, db)

    # Рассчитываем расходы по категориям
    expenses_by_category = {}
    for receipt in trip.receipts:
        category = SimpleDocumentGenerator._normalize_category_key(receipt.category)
        if category not in expenses_by_category:
            expenses_by_category[category] = 0
        expenses_by_category[category] += receipt.amount or 0

    # Рассчитываем суточные
    per_diem_days = calculate_per_diem_days(
        trip.date_from,
        trip.date_to,
        trip.departure_time,
        trip.arrival_time
    )

    per_diem_total = per_diem_days * current_user.per_diem_rate
    days = (trip.date_to - trip.date_from).days + 1
    per_diem_deduction = (
        trip.meals_breakfast_count * 0.15 +
        trip.meals_lunch_count * 0.30 +
        trip.meals_dinner_count * 0.30
    ) * per_diem_total / days if days > 0 else 0

    per_diem_to_pay = per_diem_total - per_diem_deduction

    # Общие расходы
    total_receipts_amount = sum(expenses_by_category.values())
    total_expenses = total_receipts_amount + per_diem_to_pay
    to_return = trip.advance_rub - total_expenses

    # Проверка на ошибки
    warnings = []
    errors = []

    if not trip.receipts or len(trip.receipts) == 0:
        errors.append("Не загружено ни одного чека")

    if total_receipts_amount == 0:
        warnings.append("У всех чеков нулевая сумма")

    if not trip.departure_time or not trip.arrival_time:
        warnings.append("Не указано время выезда/приезда - суточные могут быть рассчитаны неправильно")

    if total_expenses == 0:
        errors.append("Нет расходов для документов (ни чеки, ни суточные)")

    return {
        "trip_id": trip_id,
        "destination": trip.destination_city,
        "dates": f"{trip.date_from.strftime('%d.%m.%Y')} - {trip.date_to.strftime('%d.%m.%Y')}",
        "receipts_count": len(trip.receipts),
        "expenses_by_category": expenses_by_category,
        "per_diem_days": per_diem_days,
        "per_diem_total": per_diem_total,
        "per_diem_deduction": per_diem_deduction,
        "per_diem_to_pay": per_diem_to_pay,
        "total_receipts_amount": total_receipts_amount,
        "total_expenses": total_expenses,
        "advance_rub": trip.advance_rub,
        "to_return": to_return,
        "warnings": warnings,
        "errors": errors,
        "can_generate": len(errors) == 0
    }


@router.post("/{trip_id}/generate")
async def generate_documents(
    trip_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Сгенерировать все документы для командировки"""

    logger.info(f"[GENERATE] Starting generation for trip_id={trip_id}, user={current_user.username}")

    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id
    ).first()

    if not trip:
        logger.error(f"[GENERATE] Trip {trip_id} not found for user {current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )

    logger.info(f"[GENERATE] Trip found: {trip.destination_city}, receipts: {len(trip.receipts)}")

    # Lazy-обработка: добираем суммы/даты из файлов, если еще не распознаны
    _fill_missing_receipt_data(trip.receipts, db)

    try:
        # Собираем данные для генерации
        trip_data = {
            'fio': current_user.fio,
            'tab_no': current_user.tab_no,
            'department': current_user.department,
            'position': current_user.position,
            'org_name': current_user.org_name,
            'destination_city': trip.destination_city,
            'destination_org': trip.destination_org,
            'date_from': trip.date_from,
            'date_to': trip.date_to,
            'departure_time': trip.departure_time,
            'arrival_time': trip.arrival_time,
            'purpose': trip.purpose,
            'days': (trip.date_to - trip.date_from).days + 1,
            'per_diem_rate': current_user.per_diem_rate,
            'meals_breakfast_count': trip.meals_breakfast_count,
            'meals_lunch_count': trip.meals_lunch_count,
            'meals_dinner_count': trip.meals_dinner_count,
            'advance_rub': trip.advance_rub,
            'receipts': [
                {
                    'category': r.category,
                    'amount': r.amount,
                    'date': r.receipt_date,
                    'org_name': r.org_name,
                    'file_path': r.file_path
                }
                for r in trip.receipts
            ]
        }

        # Рассчитываем расходы по категориям
        expenses_by_category = {}
        for receipt in trip.receipts:
            category = SimpleDocumentGenerator._normalize_category_key(receipt.category)
            if category not in expenses_by_category:
                expenses_by_category[category] = 0
            expenses_by_category[category] += receipt.amount or 0

        trip_data['expenses_by_category'] = expenses_by_category

        # Рассчитываем суточные
        per_diem_days = calculate_per_diem_days(
            trip.date_from,
            trip.date_to,
            trip.departure_time,
            trip.arrival_time
        )

        per_diem_total = per_diem_days * current_user.per_diem_rate
        per_diem_deduction = (
            trip.meals_breakfast_count * 0.15 +
            trip.meals_lunch_count * 0.30 +
            trip.meals_dinner_count * 0.30
        ) * per_diem_total / trip_data['days'] if trip_data['days'] > 0 else 0

        per_diem_to_pay = per_diem_total - per_diem_deduction

        # Общие расходы
        total_expenses = sum(expenses_by_category.values()) + per_diem_to_pay
        to_return = trip.advance_rub - total_expenses

        trip_data.update({
            'per_diem_days': per_diem_days,
            'per_diem_total': per_diem_total,
            'per_diem_deduction': per_diem_deduction,
            'per_diem_to_pay': per_diem_to_pay,
            'total_expenses': total_expenses,
            'to_return': to_return
        })

        # ВАЛИДАЦИЯ: Проверяем что есть чеки с суммами
        if not trip.receipts or len(trip.receipts) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Невозможно создать документы без чеков. Загрузите хотя бы один чек."
            )

        total_amount = sum(r.amount or 0 for r in trip.receipts)
        if total_amount == 0 and per_diem_to_pay == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="У всех чеков нулевая сумма и нет суточных. Отредактируйте чеки или добавьте информацию о времени выезда/приезда."
            )

        # Преобразуем относительные пути в абсолютные для генератора
        logger.info(f"[GENERATE] Converting receipt paths to absolute")
        for receipt in trip_data['receipts']:
            if 'file_path' in receipt:
                rel_path = Path(receipt['file_path'])
                if not rel_path.is_absolute():
                    receipt['file_path'] = str(settings.BASE_DIR / rel_path)
                logger.info(f"[GENERATE]   Receipt: {receipt['file_path']}")

        # Генерируем документы упрощенным генератором
        logger.info(f"[GENERATE] Creating SimpleDocumentGenerator")
        generator = SimpleDocumentGenerator(settings.TEMPLATES_DIR, settings.OUTPUT_DIR)

        logger.info(f"[GENERATE] Calling generator.generate_all()")
        result = generator.generate_all(trip_data)
        logger.info(f"[GENERATE] Generation successful: {result}")
        return {
            "message": "Documents generated successfully",
            "files": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GENERATE] Generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating documents: {str(e)}"
        )


@router.get("/{trip_id}/download")
async def download_trip_package(
    trip_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Скачать ZIP архив с документами командировки"""

    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id
    ).first()

    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )

    # Путь к ZIP файлу
    folder_name = f"{trip.date_from.strftime('%Y-%m-%d')}_{trip.destination_city}_{current_user.fio.split()[0]}"
    zip_path = settings.OUTPUT_DIR / f"{folder_name}.zip"

    if not zip_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documents not generated yet. Please generate them first."
        )

    return FileResponse(
        path=zip_path,
        media_type='application/zip',
        filename=f"{folder_name}.zip"
    )
