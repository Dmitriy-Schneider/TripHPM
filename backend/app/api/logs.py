"""
API endpoint для логирования с фронтенда
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import logging
from ..models.user import User
from ..utils.auth import get_current_active_user

router = APIRouter()

# Настройка логгера для фронтенда
frontend_logger = logging.getLogger("frontend")
frontend_logger.setLevel(logging.DEBUG)

# Создаём handler для файла
if not frontend_logger.handlers:
    handler = logging.FileHandler("frontend.log", encoding='utf-8')
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    frontend_logger.addHandler(handler)


class LogEntry(BaseModel):
    level: str  # 'info', 'warn', 'error', 'debug'
    message: str
    context: Optional[dict] = None
    url: Optional[str] = None
    user_agent: Optional[str] = None


@router.post("/log")
async def log_from_frontend(
    log_entry: LogEntry,
    request: Request,
    current_user: Optional[User] = Depends(get_current_active_user)
):
    """
    Принимает логи с фронтенда и записывает в файл
    """
    # Формируем сообщение
    user_id = current_user.id if current_user else "anonymous"
    username = current_user.username if current_user else "anonymous"

    log_message = f"[USER:{username}] {log_entry.message}"

    if log_entry.context:
        log_message += f" | Context: {log_entry.context}"

    if log_entry.url:
        log_message += f" | URL: {log_entry.url}"

    # Записываем в лог с нужным уровнем
    level = log_entry.level.lower()
    if level == 'error':
        frontend_logger.error(log_message)
    elif level == 'warn':
        frontend_logger.warning(log_message)
    elif level == 'debug':
        frontend_logger.debug(log_message)
    else:
        frontend_logger.info(log_message)

    return {"status": "logged"}
