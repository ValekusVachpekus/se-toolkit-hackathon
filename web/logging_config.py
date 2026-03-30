import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_level: str = "INFO"):
    """
    Настройка логирования для web-панели.
    
    Логи пишутся:
    - В файл logs/web.log (max 10MB, 5 ротаций)
    - В файл logs/web_errors.log (только ERROR и выше)
    - В stdout (для Docker logs)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Удаляем существующие handlers
    root_logger.handlers.clear()
    
    # Форматтер
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    
    # 1. Console handler (для Docker logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 2. File handler (все логи)
    file_handler = RotatingFileHandler(
        LOG_DIR / "web.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 3. Error file handler (только ошибки)
    error_handler = RotatingFileHandler(
        LOG_DIR / "web_errors.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # Отключаем verbose логи от библиотек
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    logging.info("Логирование настроено: %s", LOG_DIR.absolute())


def get_logger(name: str) -> logging.Logger:
    """Получить logger для модуля."""
    return logging.getLogger(name)
