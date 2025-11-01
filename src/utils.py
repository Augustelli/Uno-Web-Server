import json
from typing import Dict, Any, Union

def serialize_message(message: Union[Dict[str, Any], str, bytes, bytearray]) -> str:
    """
    Serializa un mensaje para envío por socket.
    - Si es dict -> JSON objeto + '\n'
    - Si es str que YA es un JSON objeto (empieza con '{' y termina con '}') -> lo devuelve normalizado + '\n'
    - Si es bytes/bytearray -> decodifica a str y reintenta
    - Para cualquier otro str -> lo envuelve en un objeto {"type": "TEXT", "payload": str}
    """
    # Normalizar bytes -> str
    if isinstance(message, (bytes, bytearray)):
        message = message.decode("utf-8", errors="replace")

    # Si ya es dict, serializamos normal
    if isinstance(message, dict):
        return json.dumps(message, ensure_ascii=False) + "\n"

    # Si es str, puede ser ya JSON de objeto o texto crudo
    if isinstance(message, str):
        s = message.strip()
        # Si parece un objeto JSON, lo devolvemos tal cual (asegurando '\n')
        if s.startswith("{") and s.endswith("}"):
            return s + ("\n" if not s.endswith("\n") else "")
        # Si es texto suelto, lo envolvemos como objeto para no romper el cliente/servidor
        wrapper = {"type": "TEXT", "payload": message}
        return json.dumps(wrapper, ensure_ascii=False) + "\n"

    # Cualquier otro tipo: error explícito para no enviar basura
    raise TypeError(f"serialize_message: tipo no soportado: {type(message).__name__}")


def deserialize_message(msg_str: Union[str, bytes, bytearray]) -> Dict[str, Any]:
    """
    Deserializa un string JSON (o bytes) a dict.
    Solo devuelve dict; si el JSON es un primitivo (str/num), levanta ValueError.
    """
    if isinstance(msg_str, (bytes, bytearray)):
        msg_str = msg_str.decode("utf-8", errors="replace")

    obj = json.loads(msg_str)
    if not isinstance(obj, dict):
        raise ValueError("deserialize_message: el JSON recibido no es un objeto (dict).")
    return obj
