import socket
import threading
import sys
from utils import validate_command, serialize_message, deserialize_message

class Client:
    def __init__(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        threading.Thread(target=self.listen_server, daemon=True).start()

    def listen_server(self):
        try:
            while True:
                data = self.sock.recv(1024).decode('utf-8')
                if not data:
                    break
                msg = deserialize_message(data)
                print(f"[Server] {msg}")
        except Exception as e:
            print(f"Error recepción: {e}", file=sys.stderr)

    def send(self, cmd_str):
        try:
            cmd = validate_command(cmd_str)
            msg = serialize_message(cmd)
            self.sock.sendall(msg.encode('utf-8'))
        except ValueError as ve:
            print(ve)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Cliente UNO')
    parser.add_argument('--host', type=str, default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()

    client = Client(args.host, args.port)
    print("Conectado al servidor de UNO. Ingresa comandos: 'JUEGO <COLOR> <VALOR>' o 'DIBUJA'.")
    while True:
        try:
            cmd = input('> ')
            client.send(cmd)
        except KeyboardInterrupt:
            print("Desconectando...")
            client.sock.close()
            sys.exit(0)