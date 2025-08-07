import os
import signal
import json
from datetime import datetime

def logger_process(recv_pipe, log_path):
    """
    Proceso logger: recibe eventos vía pipe y escribe en log_path.
    """
    running = True

    def handle_signal(signum, frame):
        nonlocal running
        running = False

    # Preparar log file
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log_fp = open(log_path, 'a')

    # Señales para shutdown
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while running:
        try:
            if recv_pipe.poll(1):
                event = recv_pipe.recv()
                timestamp = datetime.now().isoformat()
                line = f"{timestamp} | {json.dumps(event)}\n"
                log_fp.write(line)
                log_fp.flush()
        except EOFError:
            break

    log_fp.close()
    print("Logger finalizado.")
