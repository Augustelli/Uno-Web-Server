import logging
import logging.handlers
from multiprocessing import Process, Queue, get_context
from typing import Optional

LOG_FORMAT = "%(asctime)s %(levelname)s %(processName)s %(threadName)s %(name)s [game=%(game_id)s player=%(player_id)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _configure_file_handler(log_path: str) -> logging.Handler:
    h = logging.handlers.RotatingFileHandler(
        filename=log_path,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    h.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    h.setLevel(logging.INFO)
    return h


def _configure_console_handler() -> logging.Handler:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    h.setLevel(logging.INFO)
    return h


def logger_worker(queue: Queue, log_path: str, also_console: bool = True) -> None:
    """
    Proceso separado que consume LogRecords desde 'queue' y los escribe con handlers locales.
    Usa un sentinel 'None' para terminar.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = []  # limpiar

    root.addHandler(_configure_file_handler(log_path))
    if also_console:
        root.addHandler(_configure_console_handler())

    # Bucle de consumo: espera LogRecord o sentinel None
    while True:
        record = queue.get()
        if record is None:  # sentinel de apagado
            break
        try:
            logger = logging.getLogger(record.name)
            logger.handle(record)
        except Exception:
            # Evitar que un fallo en un registro tumbe el proceso logger
            root.exception("Fallo manejando LogRecord")


def start_logging_process(log_path: str, also_console: bool = True) -> Queue:
    """
    Crea la Queue y lanza el proceso logger. Devuelve la Queue para que los productores envíen LogRecords.
    """
    ctx = get_context("spawn")  # más seguro multiplataforma
    q: Queue = ctx.Queue(-1)
    p: Process = ctx.Process(target=logger_worker, args=(q, log_path, also_console), daemon=True)
    p.start()
    return q


def configure_queue_logging_producer(queue: Queue) -> None:
    """
    Configura el proceso productor (server/hilos) para mandar logs a la Queue.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = []
    qh = logging.handlers.QueueHandler(queue)
    qh.setLevel(logging.INFO)
    root.addHandler(qh)


def get_logger(name: Optional[str] = None) -> logging.LoggerAdapter:
    base = logging.getLogger(name or __name__)
    return logging.LoggerAdapter(base, {"game_id": "-", "player_id": "-"})


class BoundLogger(logging.LoggerAdapter):
    def bind(self, **kwargs):
        extra = {**self.extra, **kwargs}
        return BoundLogger(self.logger, extra)


def get_bound_logger(name: Optional[str] = None, **kwargs) -> BoundLogger:
    base = logging.getLogger(name or __name__)
    return BoundLogger(base, {"game_id": "-", "player_id": "-", **kwargs})
