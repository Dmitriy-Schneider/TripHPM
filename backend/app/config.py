"""
Конфигурация приложения
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List


class Settings(BaseSettings):
    """Настройки приложения"""

    # Основные
    APP_NAME: str = "Trip Report System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # База данных
    DATABASE_URL: str = "sqlite:///./trip_reports.db"

    # Безопасность
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Пути
    BASE_DIR: Path = Path(__file__).parent.parent
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    OUTPUT_DIR: Path = BASE_DIR / "outputs"

    # Сервер
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://localhost:5173",
        "*"  # Разрешить все для локальной разработки
    ]

    # Регистрация
    ALLOW_REGISTRATION: bool = True
    REQUIRE_EMAIL_VERIFICATION: bool = False

    # Константы организации (можно переопределить через .env)
    DEFAULT_ORG_NAME: str = "ООО «ВЭМ»"
    DEFAULT_PER_DIEM_RATE: float = 2000.0
    DEFAULT_DEPARTURE_CITY: str = "Самара"

    # Пользовательская директория для сохранения документов
    # Если указана - документы будут сохраняться туда вместо outputs/
    CUSTOM_OUTPUT_DIR: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Создаем директории при инициализации
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Глобальный экземпляр настроек
settings = Settings()
