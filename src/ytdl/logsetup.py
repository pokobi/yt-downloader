import logging
import sys
from logging.handlers import RotatingFileHandler

from ytdl.paths import LOG_DIR


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if sys.stderr is not None:  # pythonw / exe(windowed) では stderr が無い
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    def _excepthook(exc_type, exc, tb):
        logging.getLogger("crash").error("未処理の例外", exc_info=(exc_type, exc, tb))

    sys.excepthook = _excepthook
