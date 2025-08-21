import random
import queue
import threading
import json
from typing import Dict, List, Tuple


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
                # Una copia de cada carta
                self.cards.append(Card(color, value))

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
    def __init__(self, max_players: int = 4, turn_timeout: int = 90):
        self.max_players = max_players
        self.turn_timeout = turn_timeout
        self.player_conns: Dict[int, 'socket.socket'] = {}
        self.hands: Dict[int, List[Card]] = {}
        self.deck = Deck()
        self.discard_pile: List[Card] = []
        self.current_turn: int = 1
        self.action_queue: queue.Queue[Tuple[int, Dict]] = queue.Queue()
        self.winner: int = 0
        self._stop_event = threading.Event()

    def add_player(self, player_id: int, conn) -> None:
        self.player_conns[player_id] = conn
        self.hands[player_id] = []

    def start_game(self) -> None:
        # Prepare deck and hands
        self.deck.shuffle()
        print("Mazo barajado.")
        for pid in self.player_conns:
            self.hands[pid] = self.deck.draw(7)
            print(f"Jugador {pid} recibe 7 cartas.")
        # Initialize discard pile
        top_card = self.deck.draw(1)
        if top_card:
            self.discard_pile.append(top_card[0])
        # Broadcast initial state
        for pid, conn in self.player_conns.items():
            conn.sendall(self._make_update(pid))
        # Main game loop
        while not self._check_winner():
            self._play_turn()
        # Game ended, announce
        for pid, conn in self.player_conns.items():
            msg = {"type": "END", "payload": {"winner": self.winner}}
            conn.sendall(self._serialize(msg))
        self._stop_event.set()

    def _play_turn(self):
        print(f"Jugando turno del jugador {self.current_turn}.")
        current_player_id = self.current_turn
        current_conn = self.player_conns[current_player_id]
        has_drawn = False

        # Notify current player
        self._broadcast_event({"event": "turn", "player": current_player_id})

        while True:  # Allow multiple actions per turn
            try:
                player_id, msg = self.action_queue.get(timeout=self.turn_timeout)
                self.action_queue.task_done()

                if player_id != current_player_id:
                    current_conn.sendall(self._serialize({"type": "ERROR", "payload": "No es tu turno."}))
                    continue

                if msg["action"] == "JUEGO":
                    # Parse card from msg
                    card = Card(msg["color"], msg["value"])
                    print(f"Jugador {current_player_id} juega: {card}")
                    self._play_card(current_player_id, card)
                    break  # Turn ends after playing a card
                elif msg["action"] == "LEVANTAR":
                    if not has_drawn:
                        drawn_cards = self.deck.draw(1)
                        if drawn_cards:
                            self.hands[current_player_id].extend(drawn_cards)
                            has_drawn = True
                            print(f"Jugador {current_player_id} levanta 1 carta")
                            # Send updated hand to player
                            current_conn.sendall(self._make_update(current_player_id))
                    else:
                        current_conn.sendall(
                            self._serialize({"type": "ERROR", "payload": "Ya levantaste una carta este turno."}))
                elif msg["action"] == "PASAR":
                    if has_drawn:
                        print(f"Jugador {current_player_id} pasa el turno")
                        break
                    else:
                        current_conn.sendall(
                            self._serialize({"type": "ERROR", "payload": "Debes levantar una carta antes de pasar."}))
                elif msg["action"] == "DIBUJA":
                    hand_msg = {
                        "type": "HAND",
                        "payload": {
                            "cards": [str(c) for c in self.hands[current_player_id]],
                            "count": len(self.hands[current_player_id]),
                            "top": str(self.discard_pile[-1])
                        }
                    }
                    current_conn.sendall(self._serialize(hand_msg))
                else:
                    current_conn.sendall(self._serialize({"type": "ERROR", "payload": "Acción desconocida."}))
            except queue.Empty:
                self._broadcast_event({"event": "timeout", "player": current_player_id})
                break

        # Advance turn
        self.current_turn = self._next_player_id()

    def _next_player_id(self):
        # Returns the next player ID in round-robin order
        ids = sorted(self.player_conns.keys())
        idx = ids.index(self.current_turn)
        return ids[(idx + 1) % len(ids)]

    def handle_action(self, player_id: int, msg: Dict) -> None:
        # Called by ClientHandler threads
        self.action_queue.put((player_id, msg))

    def get_update(self, player_id: int) -> bytes:
        return self._make_update(player_id)

    def wait_end(self) -> None:
        self._stop_event.wait()

    def _check_winner(self) -> bool:
        for pid, hand in self.hands.items():
            if not hand:
                self.winner = pid
                return True
        return False

    def _play_card(self, pid: int, card: Card) -> None:
        # Validate
        top = self.discard_pile[-1]
        if card.color == top.color or card.value == top.value:
            # Valid play
            self.hands[pid].remove(card)
            self.discard_pile.append(card)
            event = {"event": "play", "player": pid, "card": str(card)}
            self._broadcast_event(event)
        else:
            # Logic for invalid play
            pass

    # def _broadcast_event(self, event: Dict) -> None:
    #     disconnected = []
    #     for pid, conn in self.player_conns.items():
    #         try:
    #             conn.sendall(self._serialize({"type": "RESULT", "payload": event}))
    #         except OSError:
    #             print(f"Player {pid} disconnected.")
    #             disconnected.append(pid)
    #     for pid in disconnected:
    #         self.player_conns.pop(pid)

    def _broadcast_event(self, event: Dict) -> None:
        for pid, conn in self.player_conns.items():
            print(f"Broadcasting event: {event}")
            conn.sendall(self._serialize({"type": "RESULT", "payload": event}))

    def _make_update(self, pid: int) -> bytes:
        payload = {
            "hand": [str(c) for c in self.hands[pid]],
            "top": str(self.discard_pile[-1]),
            "current_turn": self.current_turn
        }
        return self._serialize({"type": "UPDATE", "payload": payload})

    @staticmethod
    def _serialize(msg: Dict) -> bytes:
        return (json.dumps(msg) + "\n").encode('utf-8')
