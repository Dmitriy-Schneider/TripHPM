"""
Модель командировки
"""
from sqlalchemy import Column, Integer, String, Float, Date, Time, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Trip(Base):
    """Модель командировки"""

    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Основные данные
    destination_city = Column(String, nullable=False)
    destination_org = Column(String, nullable=False)
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)

    # Время выезда/приезда (для расчета коэффициентов суточных)
    departure_time = Column(Time, nullable=True)
    arrival_time = Column(Time, nullable=True)

    # Цель командировки
    purpose = Column(Text, nullable=False)

    # Питание (количество раз за всю командировку)
    meals_breakfast_count = Column(Integer, default=0)
    meals_lunch_count = Column(Integer, default=0)
    meals_dinner_count = Column(Integer, default=0)

    # Финансы
    advance_rub = Column(Float, default=0.0)

    # Статус
    status = Column(String, default="draft")  # draft | completed | archived

    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Отношения
    user = relationship("User", back_populates="trips")
    receipts = relationship("Receipt", back_populates="trip", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Trip(id={self.id}, destination='{self.destination_city}', date={self.date_from})>"
