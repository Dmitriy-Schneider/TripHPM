"""
Модель чека/документа
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


# Типы документов
class DocumentType:
    FISCAL_RECEIPT = "fiscal"      # QR-чек с суммой (требует сумму)
    TRANSPORT_TICKET = "ticket"    # Билет с суммой (требует сумму)
    BOARDING_PASS = "boarding"     # Посадочный талон (БЕЗ суммы)
    HOTEL_INVOICE = "hotel"        # Счёт гостиницы (требует сумму)
    CONFIRMATION = "confirmation"  # Подтверждающий документ (БЕЗ суммы)
    OTHER = "other"                # Прочее (требует сумму)

    # Типы, которые НЕ требуют сумму
    NO_AMOUNT_TYPES = [BOARDING_PASS, CONFIRMATION]


class Receipt(Base):
    """Модель чека/документа расходов"""

    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)

    # Файл
    file_path = Column(String, nullable=False)
    file_name = Column(String, nullable=False)

    # Тип документа (определяет, нужна ли сумма)
    document_type = Column(String, default=DocumentType.FISCAL_RECEIPT)

    # Категория расхода (строка, допускаются пользовательские значения)
    category = Column(String, nullable=False)  # taxi | fuel | airplane | hotel | other | custom text

    # Данные чека
    amount = Column(Float, nullable=True)
    receipt_date = Column(DateTime, nullable=True)
    org_name = Column(String, nullable=True)

    # Данные из QR кода
    fn = Column(String, nullable=True)  # Фискальный номер
    fd = Column(String, nullable=True)  # Фискальный документ
    fp = Column(String, nullable=True)  # Фискальный признак
    qr_raw = Column(Text, nullable=True)  # Полная строка QR

    # Флаги
    has_qr = Column(Boolean, default=False)
    is_manual = Column(Boolean, default=False)  # Данные введены вручную
    requires_amount = Column(Boolean, default=True)  # Требуется ли сумма для этого документа

    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Отношения
    trip = relationship("Trip", back_populates="receipts")

    def __repr__(self):
        return f"<Receipt(id={self.id}, type='{self.document_type}', category='{self.category}', amount={self.amount})>"
