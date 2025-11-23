import socket
import threading
import sys
import os
import uuid
from typing import Any, Dict, Tuple, Optional
import json
from game import Game
from logger import start_db_logging_process, configure_queue_logging_producer, get_bound_logger
import select
from config import HOST, PORT, MAX_PLAYERS, TURN_TIMEOUT, LOG_DB_DSN



class GameManager:
    def __init__(self, max_players: int, turn_timeout: int):
        self.games: Dict[str, Game] = {}           # activos
        self.waiting_games: Dict[str, Game] = {}   # esperando jugadores
        self.max_players = max_players
        self.turn_timeout = turn_timeout
        self.lock = threading.Lock()

    def create_game(self) -> Tuple[str, Game]:
        with self.lock:
            game_id = str(uuid.uuid4())[:8]
            game = Game(max_players=self.max_players, turn_timeout=self.turn_timeout)
            self.waiting_games[game_id] = game
            print(f"Juego creado: {game_id}")
            return game_id, game

    def join_game(self, game_id: str) -> Tuple[Optional[str], Optional[Game]]:
        with self.lock:
            game = self.waiting_games.get(game_id)
            if not game:
                return None, None
            if len(game.player_conns) < self.max_players:
                return game_id, game
        return None, None

    def _run_game(self, game_id: str, game: Game) -> None:
        try:
            game.start_game()
        except Exception as e:
            print(f"Error running game {game_id}: {e}", file=sys.stderr)
        finally:
            with self.lock:
                self.games.pop(game_id, None)
                self.waiting_games.pop(game_id, None)
            print(f"Juego terminado: {game_id}")

    def start_game(self, game_id: str) -> None:
        with self.lock:
            game = self.waiting_games.pop(game_id, None)
            if not game:
                return
            self.games[game_id] = game

        print(f"Starting game thread for {game_id}")
        t = threading.Thread(target=self._run_game, args=(game_id, game), daemon=True)
        t.start()
        print(f"Juego comenzado (threaded): {game_id}")

    def remove_game(self, game_id: str) -> None:
        with self.lock:
            self.games.pop(game_id, None)
            self.waiting_games.pop(game_id, None)
            print(f"Juego eliminado: {game_id}")

    def list_games(self):
        with self.lock:
            games_list = []
            for gid, game in self.waiting_games.items():
                players = len(game.player_conns)
                games_list.append({
                    "game_id": gid,
                    "players": players,
                    "max_players": self.max_players,
                    "slots_available": self.max_players - players
                })
            return games_list


class ClientHandler(threading.Thread):
    """
    Un hilo por cliente; UN SOLO loop que procesa cualquier acción.
    Usamos dos makefiles: reader (r) y writer (w), texto UTF-8, line-buffered.
    """
    def __init__(self, conn: socket.socket, addr, game_manager: GameManager, log):
        super().__init__(daemon=True)
        self.conn = conn
        self.reader = conn.makefile(mode="r", buffering=1, encoding="utf-8", newline="\n")
        self.writer = conn.makefile(mode="w", buffering=1, encoding="utf-8", newline="\n")
        self.addr = addr
        self.game_manager = game_manager
        self.log = log
        self.game_id: Optional[str] = None
        self.player_id: Optional[int] = None
        self.game: Optional[Game] = None

    # ------------ IO helpers ------------
    def send_message(self, msg: dict) -> None:
        try:
            self.writer.write(json.dumps(msg) + "\n")
            self.writer.flush()
        except Exception as e:
            print(f"send_message error {self.addr}: {e}", file=sys.stderr)

    def receive_message(self) -> Optional[dict]:
        try:
            line = self.reader.readline()
        except Exception as e:
            print(f"readline error {self.addr}: {e}", file=sys.stderr)
            return None
        if not line:
            return None
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"JSON decode error from {self.addr}: {e}; line={line!r}", file=sys.stderr)
            return None
        if not isinstance(obj, dict):
            print(f"Non-object JSON from {self.addr}: {obj!r}", file=sys.stderr)
            self.send_message({"type": "ERROR", "payload": "Formato inválido: se esperaba un objeto JSON"})
            return None
        return obj

    # ------------ main loop ------------
    def run(self) -> None:
        bound = self.log.bind(game_id=self.game_id or "-", player_id=self.player_id or "-")
        try:
            while True:
                msg = self.receive_message()
                if not isinstance(msg, dict):
                    break

                action = msg.get("action")
                bound.info(f"Received action: {action}")

                # --- Menú/lobby ---
                if action == "LIST_GAMES":
                    self.list_games()
                    continue

                if action == "CREATE_GAME":
                    self.create_new_game()
                    bound = self.log.bind(game_id=self.game_id or "-", player_id=self.player_id or "1")
                    continue

                if action == "JOIN":
                    self.join_game(msg)
                    bound = self.log.bind(game_id=self.game_id or "-", player_id=self.player_id or "1")
                    continue

                # --- Acciones de juego (si ya estamos en uno) ---
                if self.game and self.player_id:
                    try:
                        # log no crítico
                        try:
                            self.send_pipe.send({
                                'event': 'command',
                                'player': self.player_id,
                                'command': msg,
                                'game_id': self.game_id
                            })
                        except Exception:
                            pass
                        # encolar acción (sin threads extra)
                        self.game.handle_action(self.player_id, msg)
                    except Exception as e:
                        bound.exception(f"Error dispatching action for player {self.player_id}: {e}", file=sys.stderr)
                else:
                    # Si no estamos en juego y acción desconocida
                    self.send_message({"type": "ERROR", "payload": "Comando inválido en lobby"})

        except Exception as e:
            bound.exception(f"Error cliente {self.addr}: {e}", file=sys.stderr)
        finally:
            bound.info(f"Conexión cerrada: {self.addr}")
            try:
                if self.game and self.player_id is not None:
                    try:
                        self.game.remove_player(self.player_id)
                    except Exception:
                        pass
                    if self.game_id:
                        with self.game.lock:
                            if len(self.game.player_conns) == 0:
                                self.game_manager.remove_game(self.game_id)
            finally:
                for f in (self.reader, self.writer):
                    try:
                        f.close()
                    except Exception:
                        pass
                try:
                    self.conn.close()
                except Exception:
                    pass

    # ------------ lobby actions ------------
    def join_game(self, msg: Dict[str, Any]) -> None:
        game_id = msg.get("game_id")
        self.game_id, self.game = self.game_manager.join_game(game_id)

        if not self.game:
            self.send_message({"type": "ERROR", "payload": "Game not found or full"})
            return

        with self.game.lock:
            self.player_id = max(self.game.player_conns.keys(), default=0) + 1
            # pasamos SOLO writer al Game
            self.game.add_player(self.player_id, self.writer)
            players_needed = self.game_manager.max_players - len(self.game.player_conns)
            should_start = (players_needed == 0)

        self.send_message({
            "type": "JOINED",
            "payload": {
                "game_id": self.game_id,
                "player_id": self.player_id,
                "players_needed": players_needed
            }
        })
        print(f"Jugador {self.player_id} entró al juego {self.game_id}")

        if should_start:
            self.game_manager.start_game(self.game_id)

    def create_new_game(self) -> None:
        try:
            self.game_id, self.game = self.game_manager.create_game()
            with self.game.lock:
                self.player_id = 1
                self.game.add_player(self.player_id, self.writer)
                players_needed = self.game_manager.max_players - 1
                should_start = (players_needed == 0)

            self.send_message({
                "type": "GAME_CREATED",
                "payload": {
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "players_needed": players_needed
                }
            })
            print(f"Player {self.player_id} created and joined game {self.game_id}")

            if should_start:
                self.game_manager.start_game(self.game_id)

        except Exception as e:
            print(f"Error creating game: {e}", file=sys.stderr)
            self.send_message({"type": "ERROR", "payload": "Failed to create game"})

    def list_games(self) -> None:
        try:
            games_list = self.game_manager.list_games()
            self.send_message({
                "type": "GAMES_LIST",
                "payload": {"games": games_list, "can_create": True}
            })
        except Exception as e:
            print(f"Error listando los juegos: {e}", file=sys.stderr)


def start_server(port: int = PORT, max_players: int = MAX_PLAYERS, turn_timeout: int = TURN_TIMEOUT) -> None:
    log = get_bound_logger("server")

    dsn = LOG_DB_DSN
    if dsn:
        try:
            queue = start_db_logging_process(dsn, also_console=True)
            configure_queue_logging_producer(queue)
            log.logger.info("DB logging process started")
        except Exception as e:
            # fallback to console logging
            import logging
            logging.basicConfig(level=logging.INFO)
            log.logger.warning("Failed to start DB logging process: %s", e)
    else:
        import  logging
        logging.basicConfig(level=logging.INFO)
        log.logger.info("No LOG_DB_DSN provided, using console logging")

    addrinfos = socket.getaddrinfo(
        HOST, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE
    )
    log.info("Iniciando servidor en %s:%d", HOST, port)
    sockets = []
    for af, socktype, proto, canonname, sa in addrinfos:
        try:
            s = socket.socket(af, socktype, proto)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if af == socket.AF_INET6:
                log.info("Configurando socket IPv6 para aceptar IPv4 también")
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            s.bind(sa)
            s.listen(128)
            sockets.append(s)
            log.info(f"Escuchando en {sa} (family {af})")
        except Exception as e:
            log.info(f"No se pudo unir {sa}: {e}", file=sys.stderr)

    log.info("Servidor listo para aceptar conexiones. Iniciando GameManager...")
    game_manager = GameManager(max_players, turn_timeout)

    try:
        while True:
            rlist, _, _ = select.select(sockets, [], [])
            for s in rlist:
                conn, addr = s.accept()
                log.info(f"Nueva conexión desde {addr}")
                handler = ClientHandler(conn, addr, game_manager, log)
                handler.start()
    except Exception as e:
        log.error(f"Error del servidor: {e}", file=sys.stderr)
    finally:
        for s in sockets:
            try:
                s.close()
            except Exception:
                pass
        log.info("Server parado.")


if __name__ == "__main__":
    start_server()
