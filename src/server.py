import socket
import threading
import sys
import os
import uuid
from multiprocessing import Pipe, Process
from typing import Any
import json
from utils import deserialize_message, serialize_message
from game import Game
from logger import logger_process
from dotenv import load_dotenv

load_dotenv()

HOST = os.environ.get("HOST", "localhost")
PORT = int(os.environ.get("PORT", 8090))
MAX_PLAYERS = int(os.environ.get("MAX_PLAYERS", 2))
TURN_TIMEOUT = int(os.environ.get("TURN_TIMEOUT", 300))


class GameManager:
    def __init__(self, max_players, turn_timeout):
        self.games = {}  # game_id -> Game instance
        self.waiting_games = {}  # game_id -> Game instance (games waiting for players)
        self.player_to_game = {}  # player_conn -> game_id
        self.max_players = max_players
        self.turn_timeout = turn_timeout
        self.lock = threading.Lock()

    def create_game(self):
        """Create a new game and return its ID"""
        with self.lock:
            game_id = str(uuid.uuid4())[:8]  # Short UUID
            game = Game(max_players=self.max_players, turn_timeout=self.turn_timeout)
            self.waiting_games[game_id] = game
            print(f"Created new game: {game_id}")
            return game_id, game

    def join_game(self, msg):
        """Join a specific game by ID"""
        game_id = msg.get("game_id")  # Specific game ID required

        if not game_id:
            error_msg = serialize_message({
                "type": "ERROR",
                "payload": "Game ID required for JOIN action"
            })
            self.conn.sendall(error_msg.encode("utf-8"))
            return

        # Try to join specific game
        with self.game_manager.lock:
            if game_id in self.game_manager.waiting_games:
                self.game = self.game_manager.waiting_games[game_id]
                if len(self.game.player_conns) < self.game_manager.max_players:
                    self.game_id = game_id
                else:
                    self.game = None

        if not self.game:
            error_msg = serialize_message({
                "type": "ERROR",
                "payload": "Game not found or full"
            })
            self.conn.sendall(error_msg.encode("utf-8"))
            return

        # Add player to game
        self.player_id = max(self.game.player_conns.keys(), default=0) + 1
        self.game.add_player(self.player_id, self.conn)

        # Send join confirmation
        join_msg = serialize_message({
            "type": "JOINED",
            "payload": {
                "game_id": self.game_id,
                "player_id": self.player_id,
                "players_needed": self.game_manager.max_players - len(self.game.player_conns)
            }
        })
        self.conn.sendall(join_msg.encode("utf-8"))
        print(f"Player {self.player_id} joined game {self.game_id}")

        # Start game if full
        if len(self.game.player_conns) == self.game_manager.max_players:
            self.game_manager.start_game(self.game_id)

    def start_game(self, game_id):
        """Move game from waiting to active games"""
        with self.lock:
            if game_id in self.waiting_games:
                game = self.waiting_games.pop(game_id)
                self.games[game_id] = game
                game.start_game()
                print(f"Started game: {game_id}")

    def remove_game(self, game_id):
        """Remove finished game"""
        with self.lock:
            self.games.pop(game_id, None)
            self.waiting_games.pop(game_id, None)
            print(f"Removed game: {game_id}")

    def list_games(self):
        """List all available games"""
        with self.lock:
            games_list = []
            for game_id, game in self.waiting_games.items():
                games_list.append({
                    "game_id": game_id,
                    "players": len(game.player_conns),
                    "max_players": self.max_players,
                    "slots_available": self.max_players - len(game.player_conns)
                })
            return games_list


class ClientHandler(threading.Thread):
    def __init__(self, conn, addr, game_manager, send_pipe):
        super().__init__(daemon=True)
        self.conn = conn
        self.conn_file = conn.makefile(mode="rw")
        self.addr = addr
        self.game_manager = game_manager
        self.send_pipe = send_pipe
        self.game_id = None
        self.player_id = None
        self.game = None

    def send_message(self, msg: dict):
        self.conn_file.write(json.dumps(msg) + "\n")
        self.conn_file.flush()

    def receive_message(self):
        line = self.conn_file.readline()
        if not line:
            return None
        return json.loads(line)

    def run(self):
        try:
            msg = self.receive_message()
            if not msg:
                return

            action = msg.get("action")

            if action == "LIST_GAMES":
                self.list_games()
                msg = self.receive_message()
                if not msg:
                    return
                action = msg.get("action")

            if action == "CREATE_GAME":
                self.create_new_game()
            elif action == "JOIN":
                self.join_game(msg)
            else:
                self.send_message({
                    "type": "ERROR",
                    "payload": "Esperado LIST_GAMES, CREATE_GAME, o JOIN"
                })
                return

            if self.game and self.player_id:
                while True:
                    msg = self.receive_message()
                    if not msg:
                        break
                    self.send_pipe.send({
                        'event': 'command',
                        'player': self.player_id,
                        'command': msg,
                        'game_id': self.game_id
                    })
                    self.game.handle_action(self.player_id, msg)

        except Exception as e:
            print(f"Error cliente {self.addr}: {e}", file=sys.stderr)
        finally:
            if self.game and self.player_id:
                self.game.remove_player(self.player_id)
                with self.game.lock:
                    if len(self.game.player_conns) == 0:
                        self.game_manager.remove_game(self.game_id)
            self.conn_file.close()
            self.conn.close()

    def join_game(self, msg: dict[str, Any]):
        game_id = msg.get("game_id")
        self.game_id, self.game = self.game_manager.join_game(game_id)

        if not self.game:
            self.send_message({
                "type": "ERROR",
                "payload": "Game not found or full"
            })
            return

        with self.game.lock:
            self.player_id = max(self.game.player_conns.keys(), default=0) + 1
            self.game.add_player(self.player_id, self.conn)

        self.send_message({
            "type": "JOINED",
            "payload": {
                "game_id": self.game_id,
                "player_id": self.player_id,
                "players_needed": self.game_manager.max_players - len(self.game.player_conns)
            }
        })

        print(f"Player {self.player_id} joined game {self.game_id}")

        if len(self.game.player_conns) == self.game_manager.max_players:
            self.game_manager.start_game(self.game_id)

        while True:
            msg = self.receive_message()
            if not msg:
                break
            self.send_pipe.send({
                'event': 'command',
                'player': self.player_id,
                'command': msg,
                'game_id': self.game_id
            })
            self.game.handle_action(self.player_id, msg)

    def create_new_game(self):
        try:
            self.game_id, self.game = self.game_manager.create_game()
            self.player_id = 1
            self.game.add_player(self.player_id, self.conn)
            self.send_message({
                "type": "GAME_CREATED",
                "payload": {
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "players_needed": self.game_manager.max_players - 1
                }
            })
            print(f"Player {self.player_id} created and joined game {self.game_id}")

            if len(self.game.player_conns) == self.game_manager.max_players:
                self.game_manager.start_game(self.game_id)

        except Exception as e:
            print(f"Error creating game: {e}")
            self.send_message({
                "type": "ERROR",
                "payload": "Failed to create game"
            })

    def list_games(self):
        try:
            games_list = self.game_manager.list_games()
            self.send_message({
                "type": "GAMES_LIST",
                "payload": {
                    "games": games_list,
                    "can_create": True
                }
            })
        except Exception as e:
            print(f"Error listing games: {e}")


def start_server(port=PORT, max_players=MAX_PLAYERS, turn_timeout=TURN_TIMEOUT):
    # Pipe para logger
    recv_pipe, send_pipe = Pipe(duplex=False)
    log_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'game.log')
    logger_proc = Process(target=logger_process, args=(recv_pipe, log_path), daemon=True)
    logger_proc.start()

    # Socket del servidor
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Allow port reuse
    sock.bind((HOST, port))
    sock.listen(10)  # Allow more connections for multiple games
    print(f"Servidor UNO escuchando en puerto {port}")

    # Game manager
    game_manager = GameManager(max_players, turn_timeout)

    try:
        while True:
            conn, addr = sock.accept()
            print(f"Nueva conexión desde {addr}")
            handler = ClientHandler(conn, addr, game_manager, send_pipe)
            handler.start()

    except Exception as e:
        print(f"Error en el servidor: {e}", file=sys.stderr)
    finally:
        sock.close()
        logger_proc.terminate()
        logger_proc.join()
        print("Servidor finalizado.")


if __name__ == "__main__":
    start_server()
