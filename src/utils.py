import re
import json
from typing import Dict, Any

# Regex patterns for commands
game_pattern = re.compile(r"^JUEGO\s+(ROJO|VERDE|AZUL|AMARILLO)\s+([0-9])$")
draw_pattern = re.compile(r"^DIBUJA$")


def validate_command(cmd: str) -> Dict[str, Any]:
    """
    Valida un comando de cliente.
    - JUEGO <COLOR> <VALOR>
    - DIBUJA

    Retorna un dict con action y parámetros o lanza ValueError.
    """
    cmd = cmd.strip().upper()
    m = game_pattern.match(cmd)
    if m:
        color, value = m.groups()
        return {"action": "JUEGO", "color": color, "value": value}
    if draw_pattern.match(cmd):
        return {"action": "DIBUJA"}
    raise ValueError(f"Comando inválido: {cmd}")


def serialize_message(message: Dict[str, Any]) -> str:
    """
    Serializa un diccionario a JSON para envío por socket.
    """
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    print(f"Serializando mensaje: {message}")
    return json.dumps(message)


def deserialize_message(msg_str: str) -> Dict[str, Any]:
    """
    Deserializa un string JSON recibido por socket a dict.
    Si recibe bytes, los decodifica primero.
    """
    if isinstance(msg_str, bytes):
        msg_str = msg_str.decode("utf-8")
    return json.loads(msg_str)