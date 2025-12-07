from multiprocessing import Queue
from typing import Any, Dict, Optional
import datetime
import json
import sys

from psycopg_pool import ConnectionPool

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
