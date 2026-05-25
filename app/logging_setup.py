"""Konfigurace `loguru` s rotujícím souborem v user data dir."""

from __future__ import annotations

import sys

from loguru import logger

from app.config import LOGS_DIR, ensure_dirs


def setup_logging(verbose: bool = False) -> None:
    """Idempotentní setup loggeru — bezpečné volat víckrát."""
    ensure_dirs()
    logger.remove()

    console_level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        level=console_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | {message}",
    )

    log_file = LOGS_DIR / "app.log"
    logger.add(
        str(log_file),
        level="DEBUG",
        rotation="5 MB",
        retention=5,
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
    )
