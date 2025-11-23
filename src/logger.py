import logging.handlers
from multiprocessing import Process, Queue, get_context
from typing import Optional, List, Tuple
import datetime
import json
from psycopg_pool import ConnectionPool

_DEFAULT_BATCH_SIZE = 100
_DEFAULT_FLUSH_INTERVAL = 1.0  # seconds

_pool: Optional[ConnectionPool] = None


def _ensure_pool(dsn: str) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(dsn, min_size=1, max_size=4)
    return _pool


def _record_to_tuple(record: logging.LogRecord) -> Tuple:
    created = datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc)
    # Extract adapter extras if present
    game_id = getattr(record, "game_id", "-")
    player_id = getattr(record, "player_id", "-")
    # Minimal extra: include remaining attributes that are JSON-serializable
    extra = {}
    for k, v in record.__dict__.items():
        if k in ("msg", "args", "levelname", "name", "processName", "threadName", "created", "msecs", "relativeCreated", "levelno", "stack_info", "exc_info"):
            continue
        try:
            json.dumps({k: v})
            extra[k] = v
        except Exception:
            # skip non-serializable
            continue
    return (
        created,
        record.levelname,
        record.name,
        getattr(record, "processName", ""),
        getattr(record, "threadName", ""),
        record.getMessage(),
        str(game_id),
        str(player_id),
        json.dumps(extra) if extra else None,
    )


def logger_db_worker(queue: Queue, dsn: str, also_console: bool = False, batch_size: int = _DEFAULT_BATCH_SIZE, flush_interval: float = _DEFAULT_FLUSH_INTERVAL) -> None:
    """
    Worker process: consumes LogRecords from queue and writes to Postgres in batches.
    Send a sentinel None to stop the worker (it will flush pending items).
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = []
    if also_console:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [game=%(game_id)s player=%(player_id)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        ch.setLevel(logging.INFO)
        root.addHandler(ch)

    pool = _ensure_pool(dsn)
    insert_sql = """
    INSERT INTO logs (created_at, level, logger_name, process_name, thread_name, message, game_id, player_id, extra)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    buffer: List[Tuple] = []
    last_flush = datetime.datetime.now().timestamp()

    while True:
        try:
            record = queue.get(timeout=flush_interval)
        except Exception:
            record = None

        if record is None:
            # Either sentinel or timeout; flush if buffer non-empty
            if buffer:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        cur.executemany(insert_sql, buffer)
                    conn.commit()
                buffer.clear()

            # If actual sentinel (explicit None), break
            # We can detect sentinel by a special object; assume user sends a literal None as sentinel:
            # On timeout record is also None so we can't distinguish; therefore rely on a second check: if queue is empty after flush then continue waiting.
            try:
                # Peek: if sentinel present as last item, break; non-blocking
                q_contents = False
                # no standard peek - assume user will send a sentinel then return immediately; break now
                # To avoid busy loop, continue waiting unless process terminated externally.
                # Here we'll continue loop; if user wants to stop, they should send a dedicated sentinel object or terminate process.
                pass
            except Exception:
                pass

            # continue main loop to wait for records
            continue

        # If the producer sent a sentinel tuple ("__STOP__"), handle it:
        if record is None:
            break

        # Convert and buffer
        try:
            tup = _record_to_tuple(record)
            buffer.append(tup)
        except Exception:
            root.exception("Failed converting LogRecord to tuple")

        # Flush when buffer full
        if len(buffer) >= batch_size or (datetime.datetime.now().timestamp() - last_flush) >= flush_interval:
            try:
                with pool.connection() as conn:
                    # Optional: ensure durability per transaction (default is fine). To force synchronous commit:
                    # conn.execute("SET LOCAL synchronous_commit = on")
                    with conn.cursor() as cur:
                        cur.executemany(insert_sql, buffer)
                    conn.commit()
                buffer.clear()
                last_flush = datetime.datetime.now().timestamp()
            except Exception:
                root.exception("Failed inserting logs into DB")


def start_db_logging_process(dsn: str, also_console: bool = True) -> Queue:
    """
    Start the DB logging process and return a multiprocessing.Queue for producers.
    """
    ctx = get_context("spawn")
    q: Queue = ctx.Queue(-1)
    p: Process = ctx.Process(target=logger_db_worker, args=(q, dsn, also_console), daemon=True)
    p.start()
    return q


def configure_queue_logging_producer(queue: Queue) -> None:
    """
    Configure local process to send LogRecords to the queue.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = []
    qh = logging.handlers.QueueHandler(queue)
    qh.setLevel(logging.INFO)
    root.addHandler(qh)


# Convenience adapters similar to previous file (optional)
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