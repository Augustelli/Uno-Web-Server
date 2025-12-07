# UNO Web Server — Descripción general

**UNO Web Server** es un proyecto didáctico para jugar **UNO** por red. Incluye un **servidor TCP** y un **cliente CLI** que se comunican con un **protocolo JSON por línea**. El objetivo es soportar **muchas partidas en simultáneo**, mantener el código **simple de entender**, y mostrar buenas prácticas de **concurrencia** en Python.

---

## ¿Qué hace?

* Permite que **varios usuarios** se conecten al servidor.
* Cada usuario puede **crear** una partida o **unirse** a una existente.
* Cuando una partida llega al cupo de jugadores, **comienza** automáticamente.
* El juego avanza por **turnos** (levantar, jugar, pasar) y el sistema envía **actualizaciones** a los jugadores.

---

## Cómo funciona (a grandes rasgos)

* El **servidor** escucha conexiones TCP (IPv4/IPv6). Por cada cliente que se conecta crea un **hilo** (thread) dedicado.
* Existe un **lobby** gestionado por `GameManager`:

  * Mantiene partidas **esperando** (`waiting_games`) y **activas** (`games`).
  * Permite **crear**, **listar** y **unirse** a partidas.
  * Al completarse el cupo, lanza un **hilo por partida** que ejecuta la lógica del juego.
* La **lógica del juego** vive en `Game`:

  * Guarda el estado (jugadores, manos, mazo, carta superior, turno).
  * Recibe las acciones de los jugadores a través de una **cola** (`Queue`) que garantiza **orden** y evita carreras.
  * Envía mensajes (`UPDATE`, `RESULT`, `END`, `ERROR`) a los jugadores.

---

## Arquitectura (componentes)

* **Server (`server.py`)**

  * Acepta conexiones.
  * Crea un `ClientHandler` (hilo) por cliente.
  * Orquesta partidas mediante `GameManager`.

* **GameManager**

  * Crea/Lista/Une partidas en el lobby.
  * Mueve partidas de “espera” a “activas”.
  * Inicia el **hilo del juego** y limpia al terminar.

* **Game (`game.py`)**

  * Hilo que ejecuta el loop del juego.
  * Cola de acciones para **serializar** comandos de jugadores.
  * Estado protegido con **lock**; IO (envío de mensajes) fuera del lock.

* **Client (CLI)**

  * Menú simple por consola.
  * Envía acciones y muestra los mensajes del servidor.
```ini


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

---

## Protocolo (muy simple)

* **JSON por línea** (cada mensaje termina en `\n`).
* Ejemplos de cliente → servidor:

  * `{"action":"LIST_GAMES"}`, `{"action":"CREATE_GAME"}`
  * `{"action":"JOIN","game_id":"abcd1234"}`
  * `{"action":"JUEGO","color":"ROJO","value":"5"}`
  * `{"action":"LEVANTAR"}`, `{"action":"PASAR"}`
* Respuestas del servidor:

  * `GAMES_LIST`, `GAME_CREATED`, `JOINED`, `UPDATE`, `RESULT`, `CARD_DRAWN`, `ERROR`, `END`.

---

## Concurrencia (por qué así)

* **Un hilo por cliente**: simple de razonar y suficiente para el alcance del proyecto.
* **Un hilo por partida**: aísla la lógica del juego y evita bloquear el lobby.
* **Cola de acciones (Queue)** en cada `Game`: garantiza **orden** y evita condiciones de carrera entre jugadores.
* **Locks**:

  * `GameManager.lock` → protege mapas del lobby.
  * `Game.lock` → protege estado interno del juego.
  * Regla: **no** hacer IO mientras un lock está tomado.

---

## Registro/Configuración

* Variables por `.env` (host, puerto, jugadores por partida, timeout por turno).
* Logging a consola y opción de **logging a base de datos** en proceso separado (si se configura).

---

## Cómo usar (resumen)

1. Arrancá el servidor:

   ```bash
   python3 src/server.py
   ```
2. En otra terminal, el cliente:

   ```bash
   python3 src/client.py
   ```
3. En el cliente: **listar**, **crear** o **unirse** a partidas y usar comandos:

   * `mano`, `juego <n>`, `levantar`, `pasar`, `salir`.

*(También podés usar Docker/Compose si el repo incluye los archivos de despliegue.)*

