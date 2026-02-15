"""
Главный файл FastAPI приложения
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import logging
import traceback
from .config import settings
from .database import engine, Base, SessionLocal, ensure_sqlite_schema
from .api import auth, trips, receipts, users, logs
from .models.user import User
from .utils.auth import get_password_hash

# Создаем таблицы
Base.metadata.create_all(bind=engine)
# Подхватываем новые колонки в SQLite без миграций
ensure_sqlite_schema()


def create_test_user():
    """Создает тестового пользователя для быстрого входа"""
    db = SessionLocal()
    try:
        # Проверяем старого тестового пользователя test_user
        test_user_old = db.query(User).filter(User.username == "test_user").first()

        # Проверяем нового test
        test_user = db.query(User).filter(User.username == "test").first()

        if test_user_old and not test_user:
            # Если есть старый test_user, создаем новый test БЕЗ email (чтобы не было конфликта)
            new_test_user = User(
                username="test",
                hashed_password=get_password_hash("test"),
                fio="Тестовый Пользователь",
                tab_no="001",
                email=None  # Без email, чтобы избежать конфликта
            )
            db.add(new_test_user)
            db.commit()
            print("[OK] Создан тестовый пользователь: test/test")
        elif test_user:
            print("[OK] Тестовый пользователь test уже существует")
        elif test_user_old:
            print("[OK] Тестовый пользователь test_user уже существует (используйте test_user/test для входа)")
        else:
            # Создаем первого тестового пользователя
            new_test = User(
                username="test",
                hashed_password=get_password_hash("test"),
                fio="Тестовый Пользователь",
                tab_no="001",
                email=None
            )
            db.add(new_test)
            db.commit()
            print("[OK] Создан тестовый пользователь: test/test")
    except Exception as e:
        print(f"Ошибка создания тестового пользователя: {e}")
        db.rollback()
    finally:
        db.close()

# Создаем приложение
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(trips.router, prefix="/trips", tags=["Trips"])
app.include_router(receipts.router, prefix="/receipts", tags=["Receipts"])
app.include_router(logs.router, prefix="/logs", tags=["Logging"])

# Статические файлы (для загрузок)
app.mount("/uploads", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="uploads")

# Статические файлы фронтенда
frontend_dir = Path(__file__).parent.parent.parent / "frontend"
app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")


logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Глобальный обработчик ошибок — возвращает JSON вместо raw traceback"""
    tb = traceback.format_exc()
    logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )


@app.on_event("startup")
async def startup_event():
    """Выполняется при запуске приложения"""
    create_test_user()


@app.get("/")
async def root():
    """Главная страница - веб интерфейс"""
    return FileResponse(str(frontend_dir / "index.html"))


@app.get("/health")
async def health():
    """Проверка здоровья приложения"""
    return {"status": "healthy"}


@app.get("/favicon.ico")
async def favicon():
    """Favicon - возвращаем пустой ответ чтобы избежать 404"""
    favicon_path = frontend_dir / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(str(favicon_path))
    # Если favicon не существует, возвращаем прозрачный 1x1 ico
    return JSONResponse(content={}, status_code=204)


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="Trip Report System Server")
    parser.add_argument("--port", type=int, default=settings.PORT, help="Port to run the server on")
    parser.add_argument("--host", type=str, default=settings.HOST, help="Host to bind to")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    args = parser.parse_args()

    print(f"[SERVER] Starting on http://{args.host}:{args.port}")
    print(f"[SERVER] Auto-reload: {'disabled' if args.no_reload else 'enabled'}")
    print(f"[SERVER] Debug mode: {settings.DEBUG}")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload and settings.DEBUG,
        reload_dirs=["app", str(frontend_dir)] if not args.no_reload else None,
        reload_includes=["*.py", "*.html", "*.css", "*.js"] if not args.no_reload else None
    )
