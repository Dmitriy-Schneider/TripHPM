"""
Модель пользователя
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class User(Base):
    """Модель пользователя системы"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Аутентификация
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    # Личные данные (для автозаполнения форм)
    fio = Column(String, nullable=False)  # Полное ФИО
    tab_no = Column(String, nullable=True)  # Табельный номер
    department = Column(String, nullable=True)  # Отдел
    position = Column(String, nullable=True)  # Должность

    # Настройки пользователя (JSON)
    org_name = Column(String, default="ООО «ВЭМ»")
    departure_city = Column(String, default="Самара")
    per_diem_rate = Column(Integer, default=2000)

    # Путь к изображению подписи
    signature_path = Column(String, nullable=True)

    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Отношения
    trips = relationship("Trip", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(username='{self.username}', fio='{self.fio}')>"
