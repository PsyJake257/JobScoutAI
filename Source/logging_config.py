import logging
from pathlib import Path

from paths import LOG_DATEI, LOG_ORDNER


def richte_logging_ein():
    LOG_ORDNER.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=LOG_DATEI,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        encoding="utf-8",
    )


def log_pfad() -> Path:
    return LOG_DATEI
