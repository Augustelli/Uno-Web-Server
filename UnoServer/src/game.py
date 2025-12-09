import socket
import os
from dotenv import load_dotenv
import random
import queue
import threading
from typing import Dict, List, Tuple, Optional, Any
from utils import serialize_message

load_dotenv()

HOST = os.environ.get("HOST", "localhost")
PORT = int(os.environ.get("PORT", 8090))
MAX_PLAYERS = int(os.environ.get("MAX_PLAYERS", 2))
TURN_TIMEOUT = int(os.environ.get("TURN_TIMEOUT", 300))
CARDS_NUMBER = int(os.environ.get("CARDS_NUMBER", 7))


class Card:
    """
    Representa una carta de UNO con color y valor.
    Colores: ROJO, VERDE, AZUL, AMARILLO
    Valores: 0-9
    """
    VALID_COLORS = {'ROJO', 'VERDE', 'AZUL', 'AMARILLO'}
    VALID_VALUES = {str(n) for n in range(10)}

    def __init__(self, color: str, value: str):
        color = color.upper()
        value = value.upper()
        if color not in Card.VALID_COLORS:
            raise ValueError(f"Color inválido: {color}")
        if value not in Card.VALID_VALUES:
            raise ValueError(f"Valor inválido: {value}")
        self.color = color
        self.value = value

    def __str__(self) -> str:
        return f"{self.color} {self.value}"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Card):
            return False
        return self.color == other.color and self.value == other.value


class Deck:
    """
    Mazo de cartas UNO: 4 colores x 10 valores = 40 cartas.
    """

    def __init__(self):
        self.cards: List[Card] = []
        self._build_deck()

    def _build_deck(self):
        self.cards.clear()
        for color in Card.VALID_COLORS:
            for value in sorted(Card.VALID_VALUES, key=int):
                # 10 copias de cada carta
                self.cards.extend([Card(color, value) for _ in range(10)])

    def shuffle(self) -> None:
        random.shuffle(self.cards)

    def draw(self, n: int = 1) -> List[Card]:
        if n < 1:
            raise ValueError("Debe dibujar al menos una carta.")
        drawn: List[Card] = []
        for _ in range(n):
            if not self.cards:
                break
            drawn.append(self.cards.pop(0))
        return drawn

    def count(self) -> int:
        return len(self.cards)

    def reset(self) -> None:
        self._build_deck()

class Game:
    def __init__(self, max_players: int, turn_timeout: int = 90,
                 game_id: Optional[str] = None,
                 analytics_queue: Optional[Any] = None):
        self.max_players = max_players
        self.turn_timeout = turn_timeout
        self.player_conns: Dict[int, 'socket.socket'] = {}
        self.player_names: Dict[int, str] = {}
        self.hands: Dict[int, List[Card]] = {}
        self.deck = Deck()
        self.discard_pile: List[Card] = []
        self.current_turn: int = 1
        self.action_queue: queue.Queue[Tuple[int, Dict]] = queue.Queue()
        self.winner: int = 0
        self._stop_event = threading.Event()
        self.lock = threading.Lock()
        self.game_id = game_id
        self.analytics_queue = analytics_queue

    def add_player(self, name : str, player_id: int, conn) -> None:
        self.player_conns[player_id] = conn
        self.player_names[player_id] = name
        self.hands[player_id] = []

    def _send(self, conn, payload) -> None:
        try:
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8", errors="replace")
            # Si no termina en '\n', lo agregamos; si ya viene de serialize_message, no hacemos nada
            if not payload.endswith("\n"):
                payload += "\n"
            conn.write(payload)
            conn.flush()
        except Exception as e:
            print(f"Error sending to client: {e}")

    def start_game(self) -> None:
        # Prepare deck and hands
        self.deck.shuffle()
        if self.analytics_queue and self.game_id:
            try:
                self.analytics_queue.put({
                    "type": "game_start",
                    "game_id": self.game_id,
                    "max_players": self.max_players,
                    "players": dict(self.player_names),
                })
            except Exception:
                pass
        print("Mazo barajado.")
        for pid in self.player_conns:
            self.hands[pid] = self.deck.draw(CARDS_NUMBER)
            print(f"Jugador {pid} recibe {CARDS_NUMBER} cartas.")
        # Initialize discard pile
        top_card = self.deck.draw(1)
        print("Carta inicial para pila de descarte:", top_card)
        if top_card:
            self.discard_pile.append(top_card[0])
            print(f"Carta inicial en pila de descarte: {top_card[0]}")
        # Broadcast initial state
        for pid, conn in self.player_conns.items():
            self._send(conn, self._make_update(pid))
        # Main game loop
        while not self._check_winner():
            self._play_turn()
        # Game ended, announce
        for pid, conn in self.player_conns.items():
            msg = serialize_message({"type": "END", "payload": {"winner": self.winner}})
            self._send(conn, msg)
        self._stop_event.set()

    def _play_turn(self):
        print(f"Jugando turno del jugador {self.current_turn}.")
        current_player_id = self.current_turn
        current_conn = self.player_conns[current_player_id]
        has_drawn = False

        # Notify current player
        self._broadcast_event({"event": "turn", "player": current_player_id})

        while True:
            try:
                player_id, msg = self.action_queue.get(timeout=self.turn_timeout)
                self.action_queue.task_done()

                if player_id != current_player_id:
                    with self.lock:
                        offender_conn = self.player_conns.get(player_id)
                    if offender_conn:
                        self._send(offender_conn, self._serialize({
                            "type": "ERROR",
                            "payload": "No es tu turno."
                        }))
                    continue

                if msg["action"] == "JUEGO":
                    card = Card(msg["color"], msg["value"])
                    print(f"Jugador {current_player_id} juega: {card}")
                    valid_play = self._play_card(current_player_id, card)
                    break
                elif msg["action"] == "LEVANTAR":
                    if not has_drawn:
                        drawn_cards = self.deck.draw(1)
                        if drawn_cards:
                            self.hands[current_player_id].extend(drawn_cards)
                            has_drawn = True
                            print(f"Jugador {current_player_id} levanta 1 carta")
                            # Send updated hand to player
                            card_msg = serialize_message({
                                "type": "CARD_DRAWN",
                                "payload": {
                                    "card": str(drawn_cards[0]),
                                    "hand": [str(c) for c in self.hands[current_player_id]]
                                }
                            })
                            if self.analytics_queue and self.game_id:
                                try:
                                    self.analytics_queue.put({
                                        "type": "draw",
                                        "game_id": self.game_id,
                                        "player_id": current_player_id,
                                        "player_name": self.player_names.get(current_player_id),
                                        "card": str(drawn_cards[0]),
                                    })
                                except Exception:
                                    pass
                            self._send(current_conn, card_msg)
                    else:
                        self._send(current_conn, self._serialize({"type": "ERROR", "payload": "Ya levantaste una carta este turno."}))
                elif msg["action"] == "PASAR":
                    if has_drawn:
                        print(f"Jugador {current_player_id} pasa el turno")
                        if self.analytics_queue and self.game_id:
                            try:
                                self.analytics_queue.put({
                                    "type": "pass",
                                    "game_id": self.game_id,
                                    "player_id": current_player_id,
                                    "player_name": self.player_names.get(current_player_id),
                                })
                            except Exception:
                                pass
                        break
                    else:
                        self._send(current_conn, self._serialize({"type": "ERROR", "payload": "Debes levantar una carta antes de pasar."}))
                elif msg["action"] == "DIBUJA":
                    hand_msg = {
                        "type": "HAND",
                        "payload": {
                            "cards": [str(c) for c in self.hands[current_player_id]],
                            "count": len(self.hands[current_player_id]),
                            "top": str(self.discard_pile[-1])
                        }
                    }
                    self._send(current_conn, self._serialize(hand_msg))
                else:
                    self._send(current_conn, self._serialize({"type": "ERROR", "payload": "Acción desconocida."}))
            except queue.Empty:
                self._broadcast_event({"event": "timeout", "player": current_player_id})
                if self.analytics_queue and self.game_id:
                    try:
                        self.analytics_queue.put({
                            "type": "timeout",
                            "game_id": self.game_id,
                            "player_id": current_player_id,
                            "player_name": self.player_names.get(current_player_id),
                        })
                    except Exception:
                        pass
                break

        self.current_turn = self._next_player_id()
        self._broadcast_full_update()

    def _next_player_id(self):
        # Returns the next player ID in round-robin order
        ids = sorted(self.player_conns.keys())
        idx = ids.index(self.current_turn)
        return ids[(idx + 1) % len(ids)]

    def handle_action(self, player_id: int, msg: Dict) -> None:
        # Called by ClientHandler threads
        self.action_queue.put((player_id, msg))

    def get_update(self, player_id: int) -> bytes:
        return self._make_update(player_id).encode('utf-8')

    def wait_end(self) -> None:
        self._stop_event.wait()

    def _check_winner(self) -> bool:
        if self.winner:
            return True
        for pid, hand in self.hands.items():
            if not hand:
                self.winner = pid

                # Evento de fin de partida
                if self.analytics_queue and self.game_id:
                    try:
                        self.analytics_queue.put({
                            "type": "game_end",
                            "game_id": self.game_id,
                            "winner_id": pid,
                            "winner_name": self.player_names.get(pid),
                            "players": dict(self.player_names),
                        })
                    except Exception:
                        pass

                return True
        return False


    def _play_card(self, pid: int, card: Card) -> bool:
        # Validate
        top = self.discard_pile[-1]
        if card.color == top.color or card.value == top.value:
            # Valid play
            self.hands[pid].remove(card)
            self.discard_pile.append(card)
            if self.analytics_queue and self.game_id:
                try:
                    self.analytics_queue.put({
                        "type": "play",
                        "game_id": self.game_id,
                        "player_id": pid,
                        "player_name": self.player_names.get(pid),
                        "card": str(card),
                    })
                except Exception:
                    pass
            event = {"event": "play", "player": pid, "card": str(card)}
            self._broadcast_event(event)
            self._broadcast_full_update()
            return True
        else:
            # Invalid play - player loses turn
            conn = self.player_conns[pid]
            error_msg = serialize_message({
                "type": "ERROR",
                "payload": f"Carta inválida. Pierdes el turno. Top: {top}, Jugaste: {card}"
            })
            self._send(conn, error_msg)
            return False

    def _broadcast_event(self, event: Dict) -> None:
        for pid, conn in self.player_conns.items():
            print(f"Broadcasting event: {event}")
            msg = serialize_message({"type": "RESULT", "payload": event})
            self._send(conn, msg)

    def _broadcast_full_update(self) -> None:
        # envía a cada jugador su mano + top + turno
        for pid, conn in self.player_conns.items():
            self._send(conn, self._make_update(pid))

    def _make_update(self, pid: int) -> str:
        payload = {
            "hand": [str(c) for c in self.hands[pid]],
            "top": str(self.discard_pile[-1]) if self.discard_pile else "No hay carta",
            "current_turn": self.current_turn,
            "players": list(self.player_conns.keys())
        }
        return serialize_message({"type": "UPDATE", "payload": payload})

    def remove_player(self, player_id: int) -> None:
        """
        Quita un jugador de la partida.
        Si después de quitarlo queda solo un jugador, ese jugador gana automáticamente.
        """
        print(f"Removing player {player_id} from game")

        with self.lock:
            # eliminamos conexiones y mano
            if player_id in self.player_conns:
                del self.player_conns[player_id]
            if player_id in self.hands:
                del self.hands[player_id]
            # si tenés nombres:
            # if hasattr(self, "player_names") and player_id in self.player_names:
            #     del self.player_names[player_id]

            remaining_players = list(self.player_conns.keys())

            # Si no queda nadie, no hay nada más que hacer
            if not remaining_players:
                print("No quedan jugadores en la partida.")
                return

            # Si queda SOLO UNO, lo declaramos ganador por abandono de los demás
            if len(remaining_players) == 1 and self.winner == 0:
                self.winner = remaining_players[0]
                print(f"Ganador por abandono: jugador {self.winner}")

        # *** Fuera del lock: mandamos el END al ganador que quedó ***
        # (usamos una copia de las estructuras para evitar problemas de concurrencia)
        remaining_conns = {}
        with self.lock:
            for pid, conn in self.player_conns.items():
                remaining_conns[pid] = conn

        if self.winner and remaining_conns:
            end_msg = serialize_message({
                "type": "END",
                "payload": {"winner": self.winner}
            })
            for pid, conn in remaining_conns.items():
                self._send(conn, end_msg)

            # Señalizamos que el juego terminó; el bucle de start_game saldrá en la
            # siguiente iteración, porque _check_winner() ahora devuelve True.
            self._stop_event.set()

    @staticmethod
    def _serialize(msg: Dict) -> str:
        return serialize_message(msg)