import socket
import threading
import sys
import os
from multiprocessing import Pipe, Process
from utils import deserialize_message, serialize_message
from game import Game
from logger import logger_process
from dotenv import load_dotenv

load_dotenv()

HOST = os.environ.get("HOST", "localhost")
PORT = int(os.environ.get("PORT", 8090))
MAX_PLAYERS = int(os.environ.get("MAX_PLAYERS", 2))
TURN_TIMEOUT= int(os.environ.get("TURN_TIMEOUT", 300))

class ClientHandler(threading.Thread):
    def __init__(self, conn, addr, player_id, game, send_pipe):
        super().__init__(daemon=True)
        self.conn = conn
        self.addr = addr
        self.player_id = player_id
        self.game = game
        self.send_pipe = send_pipe

    def run(self):
        try:
            while True:
                # data = self.conn.recv(1024).decode('utf-8')
                data = self.conn.recv(1024)
                if not data:
                    break
                # deserializar mensaje
                print(f"Data recibido del jugador {self.player_id}: {data} TYPE {type(data)}")
                msg = deserialize_message(data)
                # enviar evento al logger
                self.send_pipe.send({'event': 'command', 'player': self.player_id, 'command': msg})
                # procesar acción
                response = self.game.handle_action(self.player_id, msg)
                # broadcast update to all
                updates = self.game.get_update(self.player_id)
                for p_conn in self.game.player_conns.values():
                    p_conn.sendall(serialize_message(updates).encode("utf-8"))
                # if response.get('type') == 'END':
                #     break
        except Exception as e:
            print(f"Error cliente {self.player_id}: {e}", file=sys.stderr)
        finally:
            self.conn.close()


def start_server(port=PORT, max_players=MAX_PLAYERS, turn_timeout=TURN_TIMEOUT):
    # Pipe para logger
    recv_pipe, send_pipe = Pipe(duplex=False)
    log_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'game.log')
    logger_proc = Process(target=logger_process, args=(recv_pipe, log_path), daemon=True)
    logger_proc.start()

    # Socket del servidor
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, port))
    sock.listen(max_players)
    print(f"Servidor UNO escuchando en puerto {port}")

    # Iniciar Game
    game = Game(max_players=max_players, turn_timeout=turn_timeout)

    # Aceptar conexiones
    player_id = 1
    while player_id <= max_players:
        conn, addr = sock.accept()
        print(f"Jugador {player_id} conectado desde {addr}")
        print(f"Faltante de jugadores: {max_players - player_id} para comenzar la partida.")
        game.add_player(player_id, conn)
        print(f"Jugador añadido al juego |conn {conn} | player_id {player_id}.")
        handler = ClientHandler(conn, addr, player_id, game, send_pipe)
        handler.start()
        print(f"Handler iniciado para jugador {player_id} | addr {addr} | send_pipe {send_pipe}.")
        player_id += 1
        print(f"Nuevo player ID {player_id}.")

    print("Todos los jugadores conectados. Iniciando partida...")
    # Iniciar partida
    game.start_game()

    # Esperar fin de partida
    game.wait_end()

    # Cerrar server
    sock.close()
    logger_proc.join()
    print("Servidor finalizado.")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Servidor UNO')
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--max-players', type=int, default=MAX_PLAYERS)
    parser.add_argument('--turn-timeout', type=int, default=TURN_TIMEOUT)
    args = parser.parse_args()
    start_server(port=args.port, max_players=args.max_players, turn_timeout=args.turn_timeout)