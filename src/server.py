import socket
import threading
import sys
import os
import uuid
from multiprocessing import Pipe, Process
from typing import Any
import json
from game import Game
from logger import logger_process
from dotenv import load_dotenv

load_dotenv()

HOST = os.environ.get("HOST", "::")
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
        self.lock = threading.Lock() # Usado para evitar RACE CONDITIONS

    def create_game(self):
        """Create a new game and return its ID"""
        with self.lock:
            game_id = str(uuid.uuid4())[:8]  # Short UUID
            game = Game(max_players=self.max_players, turn_timeout=self.turn_timeout)
            self.waiting_games[game_id] = game
            print(f"Juego creado: {game_id}")
            return game_id, game

    def join_game(self, game_id):
        """Join a specific game by ID"""
        with self.lock:
            if game_id in self.waiting_games:
                game = self.waiting_games[game_id]
                if len(game.player_conns) < self.max_players:
                    return game_id, game
        return None, None

    def _run_game(self, game_id, game):
        """Wrapper to run game.start_game and ensure cleanup when it ends"""
        try:
            game.start_game()
        except Exception as e:
            print(f"Error running game {game_id}: {e}", file=sys.stderr)
        finally:
            with self.lock:
                self.games.pop(game_id, None)
                self.waiting_games.pop(game_id, None)
            print(f"Juego terminado: {game_id}")

    def start_game(self, game_id):
        """Move game from waiting to active games and start it in a new thread"""
        game = None
        with self.lock:
            if game_id in self.waiting_games:
                game = self.waiting_games.pop(game_id)
                self.games[game_id] = game

        if not game:
            return

        print(f"Starting game thread for {game_id}")
        t = threading.Thread(target=self._run_game, args=(game_id, game), daemon=True)
        t.start()
        print(f"Juego comenzado (threaded): {game_id}")

    def remove_game(self, game_id):
        """Remove finished game"""
        with self.lock:
            self.games.pop(game_id, None)
            self.waiting_games.pop(game_id, None)
            print(f"Juego eliminado: {game_id}")

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
        try:
            self.conn_file.write(json.dumps(msg) + "\n")
            self.conn_file.flush()
        except Exception:
            pass

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

            # Centralized message loop: read commands from client and forward to game
            if self.game and self.player_id:
                while True:
                    msg = self.receive_message()
                    if not msg:
                        break
                    # forward to logger/process pipeline if needed
                    try:
                        self.send_pipe.send({
                            'event': 'command',
                            'player': self.player_id,
                            'command': msg,
                            'game_id': self.game_id
                        })
                    except Exception:
                        pass
                    # let the game process the action in a background thread to avoid blocking the handler
                    try:
                        threading.Thread(target=self.game.handle_action, args=(self.player_id, msg), daemon=True).start()
                    except Exception as e:
                        print(f"Error dispatching action for player {self.player_id}: {e}", file=sys.stderr)

        except Exception as e:
            print(f"Error cliente {self.addr}: {e}", file=sys.stderr)
        finally:
            if self.game and self.player_id:
                try:
                    self.game.remove_player(self.player_id)
                except Exception:
                    pass
                with self.game.lock:
                    if len(self.game.player_conns) == 0:
                        self.game_manager.remove_game(self.game_id)
            try:
                self.conn_file.close()
            except Exception:
                pass
            try:
                self.conn.close()
            except Exception:
                pass

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
            # assign numeric player id
            self.player_id = max(self.game.player_conns.keys(), default=0) + 1
            # pass the file object so the game uses the same buffered writer/reader
            self.game.add_player(self.player_id, self.conn_file)

        self.send_message({
            "type": "JOINED",
            "payload": {
                "game_id": self.game_id,
                "player_id": self.player_id,
                "players_needed": self.game_manager.max_players - len(self.game.player_conns)
            }
        })

        print(f"Juegador {self.player_id} entro al juego {self.game_id}")

        if len(self.game.player_conns) == self.game_manager.max_players:
            self.game_manager.start_game(self.game_id)

    def create_new_game(self):
        try:
            self.game_id, self.game = self.game_manager.create_game()
            self.player_id = 1
            # pass the file object so the game uses the same buffered writer/reader
            self.game.add_player(self.player_id, self.conn_file)
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
            print(f"Error listando los juegos: {e}")



def start_server(port=PORT, max_players=MAX_PLAYERS, turn_timeout=TURN_TIMEOUT):
    # Pipes para logging
    recv_pipe, send_pipe = Pipe(duplex=False)
    log_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'game.log')
    logger_proc = Process(target=logger_process, args=(recv_pipe, log_path), daemon=True)
    logger_proc.start()

    # Get all available IPv4 and IPv6 addresses
    addrinfos = socket.getaddrinfo(
        HOST, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )
    sockets = []
    for addrinfo in addrinfos:
        af, socktype, proto, canonname, sa = addrinfo
        try:
            s = socket.socket(af, socktype, proto)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if af == socket.AF_INET6:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            s.bind(sa)
            s.listen(10)
            sockets.append(s)
            print(f"Escuchando en  {sa} (family {af})")
        except Exception as e:
            print(f"No se puedo unir {sa}: {e}")

    game_manager = GameManager(max_players, turn_timeout)

    try:
        while True:
            import select
            rlist, _, _ = select.select(sockets, [], [])
            for s in rlist:
                conn, addr = s.accept()
                print(f"Nueva conexión desde {addr}")
                handler = ClientHandler(conn, addr, game_manager, send_pipe)
                handler.start()
    except Exception as e:
        print(f"Error del servidor: {e}", file=sys.stderr)
    finally:
        for s in sockets:
            s.close()
        logger_proc.terminate()
        logger_proc.join()
        print("Server parado.")


if __name__ == "__main__":
    start_server()
