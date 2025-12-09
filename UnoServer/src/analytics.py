import os
from multiprocessing import Queue
from typing import Any, Dict, Optional, Tuple, List
import json
import sys

from fastapi import requests
from psycopg_pool import ConnectionPool
from config import VLLM_MODEL_NAME, VLLM_CHAT_URL


_pool: Optional[ConnectionPool] = None


def _ensure_pool(dsn: str) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(dsn, min_size=1, max_size=4)
    return _pool


def _upsert_player_stats(cur, player_name: str, won: bool, turns: int = 0, cards_played: int = 0) -> None:
    """
    Sube o actualiza stats básicas de un jugador.
    Para simplificar, actualizamos todo por cada fin de partida.
    """
    cur.execute(
        """
        INSERT INTO player_stats (player_name, games_played, games_won, total_turns, total_cards_played)
        VALUES (%s, 1, %s, %s, %s)
        ON CONFLICT (player_name) DO UPDATE
        SET games_played       = player_stats.games_played + 1,
            games_won          = player_stats.games_won + EXCLUDED.games_won,
            total_turns        = player_stats.total_turns + EXCLUDED.total_turns,
            total_cards_played = player_stats.total_cards_played + EXCLUDED.total_cards_played;
        """,
        (player_name, 1 if won else 0, turns, cards_played),
    )


def analytics_worker(queue: Queue, dsn: str) -> None:
    """
    Proceso separado que consume eventos de juego desde una Queue
    y los persiste en tables: games, game_events, player_stats.

    Espera dicts con al menos:
      - 'type': 'game_start' | 'play' | 'draw' | 'pass' | 'timeout' | 'game_end'
      - 'game_id': str
      - opcional: player_id, player_name, card, etc.

    Para terminar el proceso de forma ordenada, se puede enviar un sentinel:
      queue.put({"type": "__STOP__"})
    """
    pool = _ensure_pool(dsn)

    while True:
        event: Dict[str, Any] = queue.get()
        etype = event.get("type")

        if etype == "__STOP__" or event is None:
            # Fin ordenado del worker
            break

        game_id = event.get("game_id")
        if not game_id:
            # Evento mal formado, lo ignoramos
            continue

        try:
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    if etype == "game_start":
                        max_players = event.get("max_players", 0)
                        cur.execute(
                            """
                            INSERT INTO games (game_id, max_players, started_at)
                            VALUES (%s, %s, NOW())
                            ON CONFLICT (game_id) DO NOTHING;
                            """,
                            (game_id, max_players),
                        )
                        cur.execute(
                            """
                            INSERT INTO game_events (game_id, event_type)
                            VALUES (%s, %s);
                            """,
                            (game_id, "start"),
                        )

                    elif etype in ("play", "draw", "pass", "timeout"):
                        player_id = event.get("player_id")
                        player_name = event.get("player_name")
                        card = event.get("card")
                        extra = event.get("extra")

                        cur.execute(
                            """
                            INSERT INTO game_events (game_id, player_id, player_name, event_type, card, extra)
                            VALUES (%s, %s, %s, %s, %s, %s);
                            """,
                            (game_id, player_id, player_name, etype, card, json.dumps(extra) if extra else None),
                        )

                        if etype == "play":
                            # Contamos la jugada como 1 turno relevante para la partida
                            cur.execute(
                                "UPDATE games SET total_turns = total_turns + 1 WHERE game_id = %s;",
                                (game_id,),
                            )

                        # Opcional: actualizar stats simples por jugador
                        if player_name:
                            cards_played = 1 if etype == "play" else 0
                            _upsert_player_stats(
                                cur,
                                player_name=player_name,
                                won=False,
                                turns=1 if etype == "play" else 0,
                                cards_played=cards_played,
                            )

                    elif etype == "game_end":
                        winner_id = event.get("winner_id")
                        winner_name = event.get("winner_name")
                        players = event.get("players") or {}  # dict id->name

                        cur.execute(
                            """
                            UPDATE games
                            SET ended_at = NOW(), winner_player = %s
                            WHERE game_id = %s;
                            """,
                            (winner_id, game_id),
                        )

                        cur.execute(
                            """
                            INSERT INTO game_events (game_id, player_id, player_name, event_type, extra)
                            VALUES (%s, %s, %s, %s, %s);
                            """,
                            (game_id, winner_id, winner_name, "end", json.dumps({"players": players})),
                        )

                        # Actualizar stats de todos los jugadores de la partida
                        for pid, pname in players.items():
                            _upsert_player_stats(
                                cur,
                                player_name=pname,
                                won=(str(pid) == str(winner_id)),
                                turns=0,
                                cards_played=0,
                            )

                conn.commit()
        except Exception as e:
            print(f"[analytics_worker] Error procesando evento {event}: {e}", file=sys.stderr)
            continue


def _fetch_game_and_events(pool: ConnectionPool, game_id: str) -> Tuple[Tuple, List[Tuple]]:
    """
    Lee la partida y sus eventos desde la base de datos.

    Devuelve:
      - game: (game_id, started_at, ended_at, max_players, winner_player, total_turns)
      - events: lista de tuplas (ts, player_id, player_name, event_type, card, extra)
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT game_id, started_at, ended_at, max_players, winner_player, total_turns
                FROM games
                WHERE game_id = %s
                LIMIT 1;
                """,
                (game_id,),
            )
            game = cur.fetchone()
            if not game:
                raise RuntimeError(f"Game {game_id} not found in games table")

            cur.execute(
                """
                SELECT ts, player_id, player_name, event_type, card, extra
                FROM game_events
                WHERE game_id = %s
                ORDER BY ts ASC;
                """,
                (game_id,),
            )
            events = cur.fetchall()

    return game, events


def _format_game_for_llm(game: Tuple, events: List[Tuple]) -> str:
    """
    Convierte la info de la partida en un texto legible para el modelo.
    """
    game_id, started_at, ended_at, max_players, winner, total_turns = game

    lines: List[str] = []
    lines.append(f"Partida: {game_id}")
    lines.append(f"Inicio: {started_at}")
    lines.append(f"Fin: {ended_at}")
    lines.append(f"Jugadores máximos: {max_players}")
    lines.append(f"Ganador (player_id relativo): {winner}")
    lines.append(f"Turnos registrados (aprox): {total_turns}")
    lines.append("")
    lines.append("Eventos de la partida (en orden cronológico):")

    for ts, pid, pname, etype, card, extra in events:
        line = f"- {ts} | event={etype}"
        if pid is not None:
            line += f", player_id={pid}"
        if pname:
            line += f", player_name={pname}"
        if card:
            line += f", card={card}"
        # si quisieras: incluir extra
        # if extra:
        #     line += f", extra={extra}"
        lines.append(line)

    return "\n".join(lines)


def _build_llm_messages(game_text: str, question: str) -> list[dict]:
    """
    Arma los mensajes para el endpoint de chat del LLM (vLLM/OpenAI-like).
    """
    system_prompt = (
        "Eres un analista experto en partidas de UNO. "
        "Responde SIEMPRE en español, de forma clara, ordenada y breve. "
        "Usa únicamente la información de la partida que te doy como contexto."
    )

    user_prompt = (
        "A continuación tienes la información de una partida de UNO,\n"
        "incluyendo datos generales y la lista de eventos en orden cronológico.\n\n"
        "--- DATOS DE LA PARTIDA ---\n"
        f"{game_text}\n"
        "--- FIN DATOS ---\n\n"
        "TAREA:\n"
        f"{question}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _call_llm(messages: list[dict], temperature: float = 0.7, max_tokens: int = 512) -> str:
    """
    Llama al modelo LLM local (vLLM u otro) vía HTTP.

    Usa las variables de entorno / config:
      - VLLM_CHAT_URL
      - VLLM_MODEL_NAME

    Si no están configuradas, lanza excepción.
    """
    chat_url = VLLM_CHAT_URL or os.getenv("VLLM_CHAT_URL")
    model_name = VLLM_MODEL_NAME or os.getenv("VLLM_MODEL_NAME")

    if not chat_url or not model_name:
        raise RuntimeError("VLLM_CHAT_URL o VLLM_MODEL_NAME no configurados (no se puede hacer análisis)")

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
    }

    resp = requests.post(chat_url, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    try:
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Respuesta inesperada del LLM: {data}") from e


def _store_game_analysis(
    pool: ConnectionPool,
    game_id: str,
    question: str,
    answer: str,
    model_name: Optional[str],
) -> None:
    """
    Guarda el análisis del LLM en la tabla game_analysis.

    Si ya existe un análisis para ese game_id, lo pisa (última versión).
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO game_analysis (game_id, question, answer, model)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (game_id) DO UPDATE
                SET question = EXCLUDED.question,
                    answer   = EXCLUDED.answer,
                    model    = EXCLUDED.model,
                    created_at = NOW();
                """,
                (game_id, question, answer, model_name),
            )
        conn.commit()


def _analyze_finished_game(pool: ConnectionPool, game_id: str) -> None:
    """
    Pipeline de análisis para una partida ya terminada:

    1. Leer datos de la partida + eventos desde la DB.
    2. Construir el texto de contexto.
    3. Armar un prompt estándar (pregunta fija).
    4. Llamar al LLM.
    5. Guardar el análisis en game_analysis.

    Si algo falla, se loguea por stderr y se continúa.
    """
    try:
        game, events = _fetch_game_and_events(pool, game_id)
    except Exception as e:
        print(f"[analytics_worker] No se pudo leer partida {game_id} para análisis: {e}", file=sys.stderr)
        return

    game_text = _format_game_for_llm(game, events)

    # Pregunta fija simple para el proyecto. Se podría parametrizar.
    question = (
        "Resume brevemente la partida, explica por qué ganó el jugador ganador "
        "y sugiere en pocas líneas qué podrían mejorar los otros jugadores."
    )

    messages = _build_llm_messages(game_text, question)

    try:
        answer = _call_llm(messages, temperature=0.7, max_tokens=512)
    except Exception as e:
        print(f"[analytics_worker] Error llamando al LLM para game_id={game_id}: {e}", file=sys.stderr)
        return

    try:
        model_name = VLLM_MODEL_NAME or os.getenv("VLLM_MODEL_NAME")
        _store_game_analysis(pool, game_id, question, answer, model_name)
        print(f"[analytics_worker] Análisis guardado para partida {game_id}")
    except Exception as e:
        print(f"[analytics_worker] Error guardando análisis para game_id={game_id}: {e}", file=sys.stderr)
        return


# ----------------- worker principal ----------------- #

def analytics_worker(queue: Queue, dsn: str) -> None:
    """
    Proceso separado que consume eventos de juego desde una Queue
    y los persiste en tables: games, game_events, player_stats.
    Además, cuando recibe 'game_end', dispara un análisis automático
    de la partida usando un LLM local y guarda el resultado en game_analysis.

    Espera dicts con al menos:
      - 'type': 'game_start' | 'play' | 'draw' | 'pass' | 'timeout' | 'game_end'
      - 'game_id': str
      - opcional: player_id, player_name, card, etc.

    Para terminar el proceso de forma ordenada, se puede enviar un sentinel:
      queue.put({"type": "__STOP__"})
    """
    pool = _ensure_pool(dsn)

    while True:
        event: Dict[str, Any] = queue.get()
        etype = event.get("type")

        if etype == "__STOP__" or event is None:
            # Fin ordenado del worker
            break

        game_id = event.get("game_id")
        if not game_id:
            # Evento mal formado, lo ignoramos
            continue

        # Flag para saber si debemos lanzar análisis después de escribir en DB
        trigger_analysis = False

        try:
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    if etype == "game_start":
                        max_players = event.get("max_players", 0)
                        cur.execute(
                            """
                            INSERT INTO games (game_id, max_players, started_at)
                            VALUES (%s, %s, NOW())
                            ON CONFLICT (game_id) DO NOTHING;
                            """,
                            (game_id, max_players),
                        )
                        cur.execute(
                            """
                            INSERT INTO game_events (game_id, event_type)
                            VALUES (%s, %s);
                            """,
                            (game_id, "start"),
                        )

                    elif etype in ("play", "draw", "pass", "timeout"):
                        player_id = event.get("player_id")
                        player_name = event.get("player_name")
                        card = event.get("card")
                        extra = event.get("extra")

                        cur.execute(
                            """
                            INSERT INTO game_events (game_id, player_id, player_name, event_type, card, extra)
                            VALUES (%s, %s, %s, %s, %s, %s);
                            """,
                            (game_id, player_id, player_name, etype, card, json.dumps(extra) if extra else None),
                        )

                        if etype == "play":
                            # Contamos la jugada como 1 turno relevante para la partida
                            cur.execute(
                                "UPDATE games SET total_turns = total_turns + 1 WHERE game_id = %s;",
                                (game_id,),
                            )

                        # Opcional: actualizar stats simples por jugador
                        if player_name:
                            cards_played = 1 if etype == "play" else 0
                            _upsert_player_stats(
                                cur,
                                player_name=player_name,
                                won=False,
                                turns=1 if etype == "play" else 0,
                                cards_played=cards_played,
                            )

                    elif etype == "game_end":
                        winner_id = event.get("winner_id")
                        winner_name = event.get("winner_name")
                        players = event.get("players") or {}  # dict id->name

                        cur.execute(
                            """
                            UPDATE games
                            SET ended_at = NOW(), winner_player = %s
                            WHERE game_id = %s;
                            """,
                            (winner_id, game_id),
                        )

                        cur.execute(
                            """
                            INSERT INTO game_events (game_id, player_id, player_name, event_type, extra)
                            VALUES (%s, %s, %s, %s, %s);
                            """,
                            (game_id, winner_id, winner_name, "end", json.dumps({"players": players})),
                        )

                        # Actualizar stats de todos los jugadores de la partida
                        for pid, pname in players.items():
                            _upsert_player_stats(
                                cur,
                                player_name=pname,
                                won=(str(pid) == str(winner_id)),
                                turns=0,
                                cards_played=0,
                            )

                        # Marcamos que esta partida quedó "cerrada" y merece análisis
                        trigger_analysis = True

                conn.commit()
        except Exception as e:
            print(f"[analytics_worker] Error procesando evento {event}: {e}", file=sys.stderr)
            continue

        # Fuera de la transacción principal: hacemos el análisis (no queremos romper el guardado si falla el LLM).
        if trigger_analysis:
            try:
                _analyze_finished_game(pool, game_id)
            except Exception as e:
                print(f"[analytics_worker] Error inesperado en análisis de partida {game_id}: {e}", file=sys.stderr)
                continue
def start_analytics_worker(queue: Queue, dsn: str) -> None:
    from multiprocessing import Process
    worker = Process(target=analytics_worker, args=(queue, dsn), daemon=True)
    worker.start()