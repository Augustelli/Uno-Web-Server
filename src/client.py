import socket
import threading
import sys
import os
from utils import deserialize_message, serialize_message
from dotenv import load_dotenv

load_dotenv()

HOST = os.environ.get("HOST", "localhost")
PORT = int(os.environ.get("PORT", 8090))


class UnoClient:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.socket = None
        self.player_id = None
        self.game_id = None
        self.hand = []
        self.top_card = None
        self.current_turn = None
        self.players = []
        self.connected = False

    def connect(self):
        """Connect to the UNO server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            print(f"Conectado al servidor {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Error conectando al servidor: {e}")
            return False

    def disconnect(self):
        """Disconnect from server"""
        if self.socket:
            self.socket.close()
            self.connected = False
            print("Desconectado del servidor")

    def show_main_menu(self):
        """Show main menu for game selection"""
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

    def list_games(self):
        """List available games"""
        try:
            msg = serialize_message({"action": "LIST_GAMES"})
            self.socket.sendall(msg.encode("utf-8"))

            response = self.socket.recv(1024)
            data = deserialize_message(response)

            if data.get("type") == "GAMES_LIST":
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

    def create_game(self):
        """Create a new game"""
        try:
            msg = serialize_message({"action": "CREATE_GAME"})
            self.socket.sendall(msg.encode("utf-8"))

            response = self.socket.recv(1024)
            data = deserialize_message(response)

            if data.get("type") == "GAME_CREATED":
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
                print(f"Error creando juego: {data.get('payload', 'Error desconocido')}")
                return False

        except Exception as e:
            print(f"Error creando juego: {e}")
            return False

    def join_game_by_id(self, game_id):
        """Join a specific game by ID"""
        try:
            msg = serialize_message({"action": "JOIN", "game_id": game_id})
            self.socket.sendall(msg.encode("utf-8"))

            response = self.socket.recv(1024)
            data = deserialize_message(response)

            if data.get("type") == "JOINED":
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
                print(f"Error uniéndose al juego: {data.get('payload', 'Error desconocido')}")
                return False

        except Exception as e:
            print(f"Error uniéndose al juego: {e}")
            return False

    def game_setup(self):
        """Handle game setup menu"""
        while True:
            choice = self.show_main_menu()

            if choice == '1':
                # List and join game
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
                # Create new game
                if self.create_game():
                    return True

            elif choice == '3':
                # Join specific game by ID
                game_id = input("Ingresa el ID del juego: ").strip()
                if game_id:
                    if self.join_game_by_id(game_id):
                        return True
                else:
                    print("ID de juego inválido.")

            elif choice == '4':
                # Exit
                return False

    def listen_for_messages(self):
        """Listen for server messages in a separate thread"""
        while self.connected:
            try:
                data = self.socket.recv(1024)
                if not data:
                    break

                msg = deserialize_message(data)
                self.handle_server_message(msg)

            except Exception as e:
                if self.connected:
                    print(f"Error recibiendo mensaje: {e}")
                break

    def handle_server_message(self, msg):
        """Handle messages from server"""
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
        """Display current game state"""
        print(f"\n=== ESTADO DEL JUEGO ===")
        print(f"Juego ID: {self.game_id}")
        print(f"Jugadores: {self.players}")
        print(f"Carta superior: {self.top_card}")
        print(f"Tu mano ({len(self.hand)} cartas):")
        for i, card in enumerate(self.hand, 1):
            print(f"  {i}. {card}")

    def play_game(self):
        """Main game loop"""
        # Start listening thread
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
                    msg = serialize_message({"action": "LEVANTAR"})
                    self.socket.sendall(msg.encode("utf-8"))
                elif command == 'pasar':
                    msg = serialize_message({"action": "PASAR"})
                    self.socket.sendall(msg.encode("utf-8"))
                elif command.startswith('juego '):
                    try:
                        card_num = int(command.split()[1]) - 1
                        if 0 <= card_num < len(self.hand):
                            card = self.hand[card_num]
                            color, value = card.split()
                            msg = serialize_message({
                                "action": "JUEGO",
                                "color": color,
                                "value": value
                            })
                            self.socket.sendall(msg.encode("utf-8"))
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
        """Main client function"""
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
