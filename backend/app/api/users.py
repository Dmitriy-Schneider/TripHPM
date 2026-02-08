"""
API endpoints для управления пользователями
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..database import get_db
from ..models.user import User
from ..utils.auth import get_current_active_user
from ..config import settings
from pathlib import Path
import shutil

router = APIRouter()


class UserProfile(BaseModel):
    id: int
    username: str
    email: str | None
    fio: str
    tab_no: str | None
    department: str | None
    position: str | None
    org_name: str
    departure_city: str
    per_diem_rate: int
    signature_path: str | None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    fio: str | None = None
    tab_no: str | None = None
    department: str | None = None
    position: str | None = None
    org_name: str | None = None
    departure_city: str | None = None
    per_diem_rate: int | None = None


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(current_user: User = Depends(get_current_active_user)):
    """Получить профиль текущего пользователя"""
    return current_user


@router.put("/me", response_model=UserProfile)
async def update_current_user_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Обновить профиль текущего пользователя"""

    # Обновляем поля
    if user_data.fio is not None:
        current_user.fio = user_data.fio
    if user_data.tab_no is not None:
        current_user.tab_no = user_data.tab_no
    if user_data.department is not None:
        current_user.department = user_data.department
    if user_data.position is not None:
        current_user.position = user_data.position
    if user_data.org_name is not None:
        current_user.org_name = user_data.org_name
    if user_data.departure_city is not None:
        current_user.departure_city = user_data.departure_city
    if user_data.per_diem_rate is not None:
        current_user.per_diem_rate = user_data.per_diem_rate

    db.commit()
    db.refresh(current_user)

    return current_user


@router.post("/me/signature")
async def upload_signature(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Загрузить изображение подписи"""

    # Проверяем формат файла
    allowed_extensions = ['.png', '.jpg', '.jpeg']
    file_extension = Path(file.filename).suffix.lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {', '.join(allowed_extensions)} files are allowed"
        )

    # Сохраняем файл
    signatures_dir = settings.UPLOAD_DIR / "signatures"
    signatures_dir.mkdir(exist_ok=True)

    filename = f"signature_{current_user.id}{file_extension}"
    file_path = signatures_dir / filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Обновляем путь в БД
    current_user.signature_path = str(file_path)
    db.commit()

    return {
        "message": "Signature uploaded successfully",
        "path": str(file_path)
    }
