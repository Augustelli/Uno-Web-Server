import json
from typing import Dict, Any

def serialize_message(message: Dict[str, Any]) -> str:
    """
    Serializa un diccionario a JSON para envío por socket.
    """
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    print(f"Serializando mensaje: {message}")
    return json.dumps(message) + "\n"


def deserialize_message(msg_str: str) -> Dict[str, Any]:
    """
    Deserializa un string JSON recibido por socket a dict.
    Si recibe bytes, los decodifica primero.
    """
    if isinstance(msg_str, bytes):
        msg_str = msg_str.decode("utf-8")
    return json.loads(msg_str)