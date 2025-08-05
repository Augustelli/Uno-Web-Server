# UNO Multijugador Simplificado — MVP

## 1. Descripción general

**UNO Multiplayer** es un juego de cartas basado en el clásico UNO, adaptado a un entorno cliente-servidor en Python. Hasta **4 jugadores** se conectan a un servidor TCP, participan en tiempo real y compiten hasta quedarse sin cartas.

El MVP incluye:

* Servidor que gestiona la partida y turnos.
* Clientes CLI que permiten jugar (ver mano, jugar carta, robar carta).
* Timeout de turno (30 s) usando señales.
* Validación de jugadas con expresiones regulares.
* Registro de eventos en un proceso logger a través de pipes.

Se aprovechan estos tópicos del repositorio `compu2_um_2024`:

* Sockets TCP
* Threads
* Signals (SIGALRM)
* Pipes / multiprocessing
* Expresiones regulares
* Programación Orientada a Objetos
* Manejo de archivos

---

## 2. Arquitectura y componentes

```plaintext
                      +----------------+
                      |    CLIENTE     |        (4 instancias)
                      |  src/client.py |◀───────┐
                      +----------------+        |
                            ▲                   │
                            │ socket TCP        │
                            │                   │
+----------------+      +----------+      +----------+
|   LOGGER       |◀────▶| SERVIDOR |────▶|   LOGGER |
| src/logger.py  | pipe | src/server.py | pipe| src/logger.py |
+----------------+      +----------+      +----------+
        ▲                   ▲   ▲               ▲
        │                   │   │               │
        │           threads│   │threads        │
        │                   │   │               │
+----------------+      +----------------+      +----------------+
| src/utils.py   |      | src/game.py    |      | src/board.py   |
| Regex y helpers|      | Lógica UNO     |      | Tablero y mano  |
+----------------+      +----------------+      +----------------+
```

### 2.1. Archivos principales

* **src/server.py**: acepta hasta 4 conexiones, crea hilo por cliente, controla turnos y flujo de la partida.
* **src/client.py**: CLI que conecta al servidor, imprime mano, envía comandos (`JUEGO`, `DIBUJA`).
* **src/game.py**: clases centrales `Game`, `Deck`, `Card`, lógica de inicialización y avance de turnos.
* **src/board.py**: representa la mano de cada jugador y la pila de descarte.
* **src/logger.py**: proceso separado que recibe eventos (jugadas, robos, fin) y escribe en `logs/game.log`.
* **src/utils.py**: validación de comandos con regex y helpers de serialización/deserialización.

---

## 3. Protocolo de mensajes

Los mensajes entre cliente y servidor serán **JSON** con estructura mínima:

* **Cliente→Servidor**:

  ```json
  {
    "action": "JUEGO" | "DIBUJA",
    "color": "ROJO|AZUL|VERDE|AMARILLO",  # sólo en acción JUEGO
    "value": "0-9"                       # sólo en acción JUEGO
  }
  ```
* **Servidor→Cliente**:

  ```json
  {
    "type": "TURN" | "UPDATE" | "RESULT" | "END",
    "payload": {...}
  }
  ```

  * `TURN`: notifica turno a un jugador.
  * `UPDATE`: envía estado de pila de descarte y mano propia.
  * `RESULT`: información sobre jugada de otro jugador (hit/miss aplicable a UNO: carta jugada).
  * `END`: informa ganador y cierra partida.

---

## 4. Diseño de clases

### 4.1. `Card`

* **Atributos**: `color`, `value`.
* **Métodos**:

  * `__str__()` → Ej. "ROJO 5".

### 4.2. `Deck`

* **Atributos**: `cards` (lista de `Card`).
* **Métodos**:

  * `shuffle()`
  * `draw(n=1)` → retorna lista de `Card`.

### 4.3. `Game`

* **Atributos**:

  * `players` (lista de sockets/hilos)
  * `hands` (dict jugador→lista de `Card`)
  * `discard_pile` (lista de `Card`)
  * `current_turn` (índice)
* **Métodos**:

  * `start()` → reparte cartas y notifica inicio.
  * `next_turn()` → gestiona SIGALRM y pasa turno.
  * `play_card(player, card)` → valida y actualiza estado.
  * `draw_card(player)` → da carta del `Deck`.
  * `check_winner()` → determina fin.

### 4.4. `Server`

* Arranca socket listener.
* Acepta conexiones hasta 4.
* Para cada conexión, inicia `ClientHandler` en hilo.
* Ejecuta el bucle de la partida usando `Game`.

### 4.5. `ClientHandler`

* Lee mensajes JSON del cliente.
* Espera `TURN` para solicitar acción.
* Envía estado con `UPDATE`.

### 4.6. `Logger`

* Recibe eventos vía pipe:

  * `{"event": "play", "player": id, "card": "ROJO 5"}`
  * `{"event": "draw", ...}`
  * `{"event": "end", "winner": id}`
* Escribe en `logs/game.log` con timestamp.

---

## 5. Roadmap de implementación

1. **Estructura de carpetas** (inicializar repo).
2. **`Card` y `Deck`** en `src/game.py`, con tests unitarios.
3. **`utils.py`**: regex para validar `JUEGO ROJO 5` y `DIBUJA`.
4. **`logger.py`**: proceso logger con pipe (adaptar de Sniffer).
5. **`server.py`**:

   * Inicializar socket y aceptar hasta 4 conexiones.
   * Crear pipe y lanzar `Logger`.
   * Instanciar `Game`.
   * Iniciar bucle de juego: repartir, turnos, recibir comandos.
6. **`client.py`**:

   * Conexión al servidor.
   * Bucle lectura usuario y envío JSON.
   * Recepción y renderizado de mensajes.
7. **Timeout de turno**: integrar `SIGALRM` en `Game.next_turn`.
8. **Logging de eventos**: enviar a logger.
9. **Pruebas de integración** (dos clientes + servidor en localhost).
10. **Documentación**: `README.md` con uso.

---

## 6. MVP completado

* Servidor y 4 clientes pueden jugar una partida básica.
* Registro completo de eventos en `logs/game.log`.
* Timeout de 30 s por turno.
* Validación de jugadas.
* Mensajes claros y JSON.

---

*Ahora tenemos un diseño claro y los pasos para comenzar la implementación del MVP de UNO Multijugador.*
