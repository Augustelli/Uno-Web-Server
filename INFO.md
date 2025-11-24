
## 1) Objetivos del sistema

* Soportar N partidas en simultáneo** con **M jugadores** por partida.
* Evitar race conditions y bloqueos innecesarios.
* Proveer **logs trazables por partida/jugador sin frenar el juego.

---

## 2) Arquitectura (alto nivel)

```
+------------------+            TCP JSON-line            +---------------------+
|   CLI Client     |  <--------------------------------> |      Server         |
|  - input loop    |                                     | - accept sockets    |
|  - listen thread |                                     | - ClientHandler(th) |
+------------------+                                     | - GameManager       |
                                                         +----------+----------+
                                                                    |
                                                        start_game()| thread
                                                                    v
                                                         +-------------------+
                                                         |       Game        |
                                                         |  Queue[acciones]  |
                                                         |  Lock (estado)    |
                                                         |  _broadcast(...)  |
                                                         +-------------------+

                           logs (LogRecord) via mp.Queue
                              +---------------------+
                              v                     |
                      +----------------+            |
                      |  logger proc   | <----------+
                      |  RotatingFile  |
                      +----------------+
```

### Componentes

* **client.py (CLI)**: interfaz de texto, envío de acciones y recepción de eventos.
* **server.py**: acepta conexiones (IPv4/IPv6), crea un **hilo por cliente** y gestiona lobby.
* **GameManager**: crea y arranca partidas; mueve de *waiting* a *active*.
* **game.py (Game)**: una **partida por objeto**; cola de acciones + lock para estado.
* **logger.py**: proceso **separado** que consume una **multiprocessing.Queue** y escribe el log (rotativo).
* **utils.py**: helpers para (de)serialización JSON línea a línea.

---

## 3) Protocolo

**Decisión:** **JSON por línea** (terminado en `\n`, UTF-8).

**Motivación:**

* Muy fácil de depurar (copiar/pegar en consola).
* `readline()` simplifica el framing.
* JSON permite evolucionar el protocolo agregando campos sin romper clientes.

**Mensajes (resumen):**

* Cliente → Servidor:

  * `{"action": "LIST_GAMES"}`
  * `{"action": "CREATE_GAME"}`
  * `{"action": "JOIN", "game_id": "<id>"}`
  * `{"action": "JUEGO", "color": "ROJO", "value": "5"}`
  * `{"action": "LEVANTAR"}` / `{"action": "PASAR"}`
* Servidor → Cliente:

  * `GAMES_LIST`, `GAME_CREATED`, `JOINED`
  * `UPDATE` (mano/top/turno por jugador)
  * `RESULT` (eventos: `turn`, `play`, `timeout`)
  * `END` (ganador), `ERROR` (mensaje dirigido)

**Detalles de implementación que evitan bugs:**

* En el servidor usamos **dos `makefile`** por conexión: `reader("r")` y `writer("w")` (UTF-8, line-buffered).
* En el juego se guarda **solo el `writer`** (TextIO) por jugador.
* **Siempre** enviamos un **objeto** JSON (no primitivos) y **siempre** terminamos con `\n`.

**Trade-offs / Alternativas:**

* JSON agrega bytes extra vs binario (no relevante en CLI y turnos humanos).
* Alternativa futura: **WebSocket** si se quiere cliente web/tiempos reales más fluidos.

---

## 4) Concurrencia y flujo de datos

**Decisión:** *thread-per-connection* en server + **cola de acciones** en `Game`.

**Motivación:**

* Hilo por cliente simplifica lectura/escritura de sockets.
* La **cola (`queue.Queue`)** en `Game` **serializa** las acciones y **evita carreras lógicas** (un único loop consume).
* Se usa **`Lock`** solo para proteger estructuras **brevemente**.
* **Invariante clave:** **NO hacer I/O dentro del lock** (evita que un cliente lento congele la partida).

**Por qué no `asyncio` ahora:**

* Complejidad extra innecesaria para el alcance actual (CLI, decenas/centenas de conexiones).
* El diseño actual ya es consistente y fácilmente migrable si hiciera falta escalar mucho más.

**Trade-offs / Alternativas:**

* Más hilos consumen más memoria que `asyncio`.
* Alternativa: `selectors`/`asyncio` para miles de clientes o latencias ultra bajas.

---

## 5) Modelo de datos interno (Game)

* `player_conns: Dict[int, TextIO]` — escritor por jugador.
* `hands: Dict[int, List[Card]]` — mano por jugador.
* `deck: Deck` / `discard_pile: List[Card]`.
* `current_turn: int` — id de jugador activo (round-robin).
* `action_queue: Queue[(player_id, msg_dict)]` — **único** punto de entrada de acciones.
* `lock: threading.Lock` — protege **solo** estado; IO siempre **fuera** del lock.

**Eventos que disparan `UPDATE` a todos:**

* Inicio de partida.
* **Jugada válida** (`play`) → la carta sale de la mano y pasa a `discard_pile`.
* **PASAR** y **timeout** (cambio de turno).
* Acciones dirigidas (p.ej., `LEVANTAR`) envían también **mensajes privados** al actor.

**Errores dirigidos:**

* “No es tu turno” se envía **solo** al infractor (no broadcast).
* Errores de formato/acción desconocida → respuesta `ERROR` al emisor.

---

## 6) Logging (observabilidad)

**Decisión:** **proceso independiente** que consume **`multiprocessing.Queue`** de `LogRecord` (con sentinel `None` para apagado).

**Motivación:**

* El IO a disco (archivo rotativo) **no bloquea** hilos de juego/servidor.
* Posibilidad de agregar destinos (consola, archivo, syslog) sin tocar el core.
* Trazabilidad por **`game_id`** y **`player_id`** usando `LoggerAdapter`.

**Detalles:**

* Productores (server/handlers/game) usan `QueueHandler`.
* El proceso logger toma `record = queue.get()` y `logger.handle(record)`.
* Se envía `None` al cerrar para terminar limpio.

**Alternativas:**

* Logger in-process con `RotatingFileHandler` → más simple, pero puede bloquear en IO pesado.
* Centralización futura (ELK/Loki) enchufando un handler específico.

---

## 7) Red y aceptación de conexiones

* Se resuelven **IPv4/IPv6** y se **escucha en múltiples sockets**; el bucle `select` acepta en cualquiera.
* `SO_REUSEADDR` y `IPV6_V6ONLY` se configuran para mejor compatibilidad.
* Cada `accept()` lanza un **`ClientHandler`** (hilo **daemon**).

---

## 8) Configuración

* Variables en `.env` (con defaults razonables):

  * `HOST`, `PORT`, `MAX_PLAYERS`, `TURN_TIMEOUT`.
* `dotenv` carga la configuración efectiva al inicio.
* Recomendación: loguear la config resultante para trazabilidad.

---

## 9) Robustez y UX

* El servidor **valida** que todo mensaje entrante sea **objeto JSON**; de otro modo, responde `ERROR` y descarta.
* Se evita crear **hilos por acción** (la cola ya serializa).
* En `client.py`:

  * Un hilo “escucha” mensajes (`readline()`); el loop principal atiende entrada del usuario.
  * Comandos: `juego N`, `levantar`, `pasar`, `mano`, `salir`.


---



---

## 12) Escalabilidad y evolución

* El modelo actual escala bien a **decenas/centenas** de jugadores.
* Límites: *thread-per-connection* no es ideal para miles de conexiones.
* Rutas de evolución:

  1. **asyncio**/`trio` con sockets no bloqueantes.
  2. **WebSocket** + cliente web.
  3. **Persistencia** (e.g., Redis) para lobby y snapshots de partidas.
  4. **Sharding**: varios procesos *game-workers* detrás de un *acceptor*.

---

## 13) Resumen de principios guía

* **KISS del protocolo**: JSON por línea, `\n` obligatorio, objetos siempre.
* **Concurrencia segura**: cola de acciones + lock corto; **IO fuera del lock**.
* **Separación de responsabilidades**:

  * `ClientHandler`: sesión/red.
  * `GameManager`: ciclo de vida de partidas.
  * `Game`: reglas/turnos/estado.
  * `logger` separado.
* **Observabilidad**: logs con `game_id` y `player_id`.
* **Evolutivo**: listo para crecer a `asyncio`/WebSocket/persistencia si el proyecto lo requiere.

---

# Mapa de temas → dónde y cómo los usás

## Concurrencia (multithreading)

* **Dónde:** `server.py` (`ClientHandler`), `GameManager.start_game`, `client.py` (hilo oyente), `game.py` (modelo de turnos, aunque el loop del juego corre en un hilo aparte lanzado por `GameManager`).
* **Cómo:**

  * **Thread-per-connection:** un hilo `ClientHandler` por cliente para leer comandos y responder.
  * **Hilo por partida:** `GameManager.start_game()` crea un `threading.Thread` para ejecutar `game.start_game()` sin bloquear el handler.
  * **Cliente CLI:** crea un hilo `listen_for_messages` para recibir mensajes mientras el usuario escribe.
* **Primitivas usadas:** `threading.Thread`, `threading.Lock` (proteger estado del juego), `threading.Event` (en `Game` para marcar fin de partida).
* **Buenas prácticas aplicadas:** IO **fuera** del `lock`; no creás un thread por acción (usás una **Queue**).

## Estructuras de sincronización (Lock, Event, Queue)

* **Dónde:** `game.py`
* **Cómo:**

  * `threading.Lock`: protege `player_conns`, `hands`, `discard_pile`, `current_turn`.
  * `queue.Queue`: **cola de acciones** `action_queue` para serializar los comandos de los jugadores.
  * `threading.Event` (`_stop_event`): señal interna para terminar el loop del juego.
* **Comentario:** elegiste muy bien: **una sola cola** central por juego evita condiciones de carrera lógicas.

## Multiprocessing (procesos)

* **Dónde:** `logger.py` y `server.py` (arranque del logger).
* **Cómo:**

  * **Proceso de logging** separado que consume una `multiprocessing.Queue` de `LogRecord`.
  * En el servidor configurás un `QueueHandler` para mandar logs a esa queue; el proceso logger escribe a archivo (rotativo) y/o consola.
* **Beneficio:** el IO a disco del log **no** bloquea threads de juego ni handlers.

## IPC (comunicación entre procesos)

* **Dónde:** `logger.py` + `server.py`.
* **Cómo:** `multiprocessing.Queue` para pasar **LogRecord** (o datos equivalentes) del proceso principal al proceso logger.
  (En una versión anterior usabas `multiprocessing.Pipe` para eventos; hoy quedaste con `Queue` para logging, que es más estándar con `logging`.)

## Sockets (TCP, IPv4/IPv6, framing)

* **Dónde:** `server.py`, `client.py`, `game.py` (envío vía writers que vienen del socket).
* **Cómo:**

  * `socket.getaddrinfo` con `AF_UNSPEC` + `AI_PASSIVE` → escuchás en **IPv4 e IPv6**.
  * `IPV6_V6ONLY = 0` para aceptar IPv4-mapped en IPv6.
  * `select.select` para **multiplexar** varios sockets de escucha y aceptar conexiones.
  * Protocolo **JSON por línea** (`\n`-delimited, UTF-8) con `makefile(..., newline="\n", encoding="utf-8")`.
* **Buena práctica aplicada:** **dos** `makefile` (reader `"r"` y writer `"w"`) por conexión del lado server → evita problemas de **buffering**.

## Serialización / Protocolo

* **Dónde:** `utils.py`, `client.py`, `server.py`, `game.py`.
* **Cómo:**

  * `serialize_message` y `deserialize_message` garantizan **objeto JSON** + **`\n`**.
  * El server **valida** que lo recibido sea un **dict** (no primitivo) antes de usar `.get`.
* **Beneficio:** evitás “doble serialización” y errores de framing.

## Temporizadores / Timeouts

* **Dónde:** `game.py`
* **Cómo:**

  * Usás `Queue.get(timeout=TURN_TIMEOUT)` como **temporizador** de turno. Si vence, disparás evento `timeout` y avanzás el turno.
* **Comentario:** solución simple y efectiva sin `Timer`s adicionales.

## Entrada/Salida (IO) y buffers

* **Dónde:** `server.py` / `client.py` (`makefile`), `game.py` (`_send`).
* **Cómo:**

  * Text IO `makefile` en modo `"r"` y `"w"` con **line buffering** (`buffering=1`) para que **`\n` haga flush**.
  * `_send` en `Game` **no** agrega IO bajo `lock` y asegura terminar en `\n`.
* **Beneficio:** evita deadlocks sutiles y “silencios” por buffering.


