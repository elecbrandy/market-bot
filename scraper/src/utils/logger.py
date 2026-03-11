import logging
import logging.handlers
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

# ── 파일 로그 경로 ────────────────────────────────────────────────
_LOG_DIR   = Path(__file__).resolve().parents[2] / "logs"
_PLAIN_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT  = "%Y-%m-%d %H:%M:%S"

_console = Console(stderr=False)


def _build_file_handler(name: str) -> logging.handlers.RotatingFileHandler:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(
        _LOG_DIR / f"{name}.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    h.setLevel(logging.DEBUG)
    h.setFormatter(logging.Formatter(fmt=_PLAIN_FMT, datefmt=_DATE_FMT))
    return h


def get_logger(name: str = "system") -> logging.Logger:
    """
    - 콘솔: RichHandler (색상 + traceback 자동)
    - 파일:  RotatingFileHandler (순수 텍스트, DEBUG 이상)
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        rich_handler = RichHandler(
            console=_console,
            level=logging.INFO,
            show_path=False,
            show_time=False,
            show_level=False,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True,
            log_time_format=_DATE_FMT,
        )
        logger.addHandler(rich_handler)
        logger.addHandler(_build_file_handler(name))

        # 노이즈 억제
        for noisy in ("httpx", "httpcore", "asyncio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    return logger


def get_console() -> Console:
    """rich 출력이 필요한 곳에서 공유 Console 사용."""
    return _console
