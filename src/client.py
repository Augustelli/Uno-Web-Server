import socket
import threading
import json
from config import HOST, PORT


class UnoClient:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.socket = None
        self.sock_file = None
        self.player_id = None
        self.game_id = None
        self.hand = []
        self.top_card = None
        self.current_turn = None
        self.players = []
        self.connected = False

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            # Use explicit encoding and newline for line-oriented protocol
            self.sock_file = self.socket.makefile(mode="rw", encoding="utf-8", newline="\n")
            self.connected = True
            print(f"Conectado al servidor {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Error conectando al servidor: {e}")
            return False

    def disconnect(self):
        try:
            if self.sock_file:
                try:
                    self.sock_file.close()
                except Exception:
                    pass
                self.sock_file = None
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
        finally:
            self.connected = False
            print("Desconectado del servidor")

    def show_main_menu(self):
        print("\n=== MENU PRINCIPAL UNO ===")
        print("1. Ver juegos disponibles")
        print("2. Crear nuevo juego")
        print("3. Unirse a juego específico")
        print("4. Salir")

        while True:
            try:
                choice = input("\nSelecciona una opción (1-4): ").strip()
                if choice in ['1', '2', '3', '4']:
                    return choice
                print("Opción inválida. Usa 1, 2, 3 o 4.")
            except KeyboardInterrupt:
                return '4'

    def send_message(self, msg: dict):
        """
        Send JSON message. Prefer raw socket.sendall; fall back to file-like write/flush.
        """
        if not self.connected:
            raise ConnectionError("Not connected")
        payload = json.dumps(msg) + "\n"
        # Prefer raw socket
        try:
            if self.socket:
                self.socket.sendall(payload.encode("utf-8"))
                return
        except Exception:
            # fall through to file-like fallback
            pass

        # Fallback: file-like object from makefile
        try:
            if self.sock_file:
                self.sock_file.write(payload)
                self.sock_file.flush()
                return
        except Exception as e:
            raise ConnectionError(f"Failed to send message: {e}")

        raise ConnectionError("No valid connection to send message")

    def receive_message(self):
        """
        Read one JSON line from the makefile. Returns dict or None if EOF.
        """
        if not self.connected or not self.sock_file:
            return None
        try:
            line = self.sock_file.readline()
        except Exception as e:
            print(f"Error reading from server: {e}")
            return None

        print("Leyendo línea:", line)
        if not line:
            # EOF / connection closed
            print("No hay linea recibida")
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return None

    def list_games(self):
        try:
            self.send_message({"action": "LIST_GAMES"})
            data = self.receive_message()

            if data and data.get("type") == "GAMES_LIST":
                games = data["payload"]["games"]
                if not games:
                    print("\nNo hay juegos disponibles.")
                    return []

                print("\n=== JUEGOS DISPONIBLES ===")
                for i, game in enumerate(games, 1):
                    print(f"{i}. ID: {game['game_id']} - "
                          f"Jugadores: {game['players']}/{game['max_players']} - "
                          f"Espacios libres: {game['slots_available']}")
                return games
            else:
                print("Error obteniendo lista de juegos")
                return []

        except Exception as e:
            print(f"Error listando juegos: {e}")
            return []

    def create_game(self, player_number : int = 4):
        try:
            self.send_message({"action": "CREATE_GAME", "max_players": player_number})
            data = self.receive_message()

            if data and data.get("type") == "GAME_CREATED":
                payload = data["payload"]
                self.game_id = payload["game_id"]
                self.player_id = payload["player_id"]
                players_needed = payload["players_needed"]

                print(f"\n¡Juego creado exitosamente!")
                print(f"ID del juego: {self.game_id}")
                print(f"Eres el jugador {self.player_id}")
                print(f"Esperando {players_needed} jugador(es) más...")
                return True
            else:
                print(
                    f"Error creando juego: {data.get('payload', 'Error desconocido') if data else 'Sin respuesta del servidor'}")
                return False

        except Exception as e:
            print(f"Error creando juego: {e}")
            return False

    def join_game_by_id(self, game_id):
        try:
            self.send_message({"action": "JOIN", "game_id": game_id})
            data = self.receive_message()

            if data and data.get("type") == "JOINED":
                payload = data["payload"]
                self.game_id = payload["game_id"]
                self.player_id = payload["player_id"]
                players_needed = payload["players_needed"]

                print(f"\n¡Te uniste al juego exitosamente!")
                print(f"ID del juego: {self.game_id}")
                print(f"Eres el jugador {self.player_id}")
                if players_needed > 0:
                    print(f"Esperando {players_needed} jugador(es) más...")
                return True
            else:
                print(
                    f"Error uniéndose al juego: {data.get('payload', 'Error desconocido') if data else 'Sin respuesta del servidor'}")
                return False

        except Exception as e:
            print(f"Error uniéndose al juego: {e}")
            return False

    def game_setup(self):
        while True:
            choice = self.show_main_menu()

            if choice == '1':
                games = self.list_games()
                if games:
                    print("\n0. Volver al menú principal")
                    try:
                        selection = input(f"Selecciona un juego (0-{len(games)}): ").strip()
                        if selection == '0':
                            continue

                        game_index = int(selection) - 1
                        if 0 <= game_index < len(games):
                            selected_game = games[game_index]
                            if selected_game['slots_available'] > 0:
                                if self.join_game_by_id(selected_game['game_id']):
                                    return True
                            else:
                                print("El juego está lleno.")
                        else:
                            print("Selección inválida.")
                    except ValueError:
                        print("Por favor ingresa un número válido.")

            elif choice == '2':
                number_players = input("Ingresa el número máximo de jugadores (2-10): ").strip()
                if not number_players.isdigit() or not (2 <= int(number_players) <= 10):
                    print("Número de jugadores inválido. Usando valor por defecto de 4.")
                if self.create_game(int(number_players)):
                    return True

            elif choice == '3':
                game_id = input("Ingresa el ID del juego: ").strip()
                if game_id:
                    if self.join_game_by_id(game_id):
                        return True
                else:
                    print("ID de juego inválido.")

            elif choice == '4':
                return False

    def listen_for_messages(self):
        while self.connected:
            print("ESCUCHANDO MENSAJES")
            try:
                data = self.receive_message()
                if not data:
                    print("No hay data al escuchar el mensaje")
                    break
                print("Hay data al escuchar el mensaje: ", data)
                self.handle_server_message(data)
            except Exception as e:
                if self.connected:
                    print(f"Error recibiendo mensaje: {e}")
                break

    def handle_server_message(self, msg):
        msg_type = msg.get("type")
        payload = msg.get("payload", {})

        if msg_type == "UPDATE":
            self.hand = payload.get("hand", [])
            self.top_card = payload.get("top")
            self.current_turn = payload.get("current_turn")
            self.players = payload.get("players", [])

        elif msg_type == "RESULT":
            event = payload.get("event")
            if event == "turn":
                player = payload.get("player")
                if player == self.player_id:
                    print(f"\n¡Es tu turno!")
                    self.show_game_state()
                else:
                    print(f"\nTurno del jugador {player}")

            elif event == "play":
                player = payload.get("player")
                card = payload.get("card")
                print(f"Jugador {player} jugó: {card}")

            elif event == "timeout":
                player = payload.get("player")
                print(f"Jugador {player} perdió el turno por timeout")

        elif msg_type == "END":
            winner = payload.get("winner")
            if winner == self.player_id:
                print("\n¡FELICIDADES! ¡GANASTE!")
            else:
                print(f"\nJuego terminado. Ganador: Jugador {winner}")
            self.connected = False

        elif msg_type == "ERROR":
            print(f"Error: {payload}")

        elif msg_type == "CARD_DRAWN":
            card = payload.get("card")
            self.hand = payload.get("hand", [])
            print(f"Levantaste: {card}")

    def show_game_state(self):
        print(f"\n=== ESTADO DEL JUEGO ===")
        print(f"Juego ID: {self.game_id}")
        print(f"Jugadores: {self.players}")
        print(f"Carta superior: {self.top_card}")
        print(f"Tu mano ({len(self.hand)} cartas):")
        for i, card in enumerate(self.hand, 1):
            print(f"  {i}. {card}")

    def play_game(self):
        listen_thread = threading.Thread(target=self.listen_for_messages, daemon=True)
        listen_thread.start()

        print("\n¡Esperando que comience el juego...")
        print("Comandos disponibles:")
        print("- 'juego <número>': Jugar carta por número de posición")
        print("- 'levantar': Levantar una carta del mazo")
        print("- 'pasar': Pasar turno (solo después de levantar)")
        print("- 'mano': Ver tu mano actual")
        print("- 'salir': Salir del juego")

        while self.connected:
            try:
                command = input().strip().lower()
                if command == 'salir':
                    break
                elif command == 'mano':
                    self.show_game_state()
                elif command == 'levantar':
                    self.send_message({"action": "LEVANTAR"})
                elif command == 'pasar':
                    self.send_message({"action": "PASAR"})
                elif command.startswith('juego '):
                    try:
                        card_num = int(command.split()[1]) - 1
                        if 0 <= card_num < len(self.hand):
                            card = self.hand[card_num]
                            color, value = card.split()
                            self.send_message({
                                "action": "JUEGO",
                                "color": color,
                                "value": value
                            })
                        else:
                            print("Número de carta inválido")
                    except (ValueError, IndexError):
                        print("Uso: juego <número>")
                else:
                    print("Comando no reconocido")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error enviando comando: {e}")
                break

    def run(self):
        if not self.connect():
            return
        try:
            if self.game_setup():
                self.play_game()
        finally:
            self.disconnect()


def main():
    client = UnoClient()
    client.run()


if __name__ == "__main__":
    main()
