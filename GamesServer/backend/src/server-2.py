import json
import os
from typing import List, Optional

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Body, Query
from pydantic import BaseModel
from config import DB_DSN

# =========================
# Configuración
# =========================
DB_DSN = "dbname=game_db user=postgres password=Sup3rSecret0 host=localhost port=5432"
LLM_URL = os.getenv("LLM_URL", "http://localhost:9000/v1/chat/completions")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")

app = FastAPI(title="UNO Analytics API", version="1.0.0")

# Pool global de conexiones asyncpg
db_pool: Optional[asyncpg.Pool] = None


# =========================
# Modelos de respuesta
# =========================

class GameEvent(BaseModel):
    ts: str
    player_id: Optional[int]
    player_name: Optional[str]
    event_type: str
    card: Optional[str]
    extra: Optional[dict]


class GameSummary(BaseModel):
    game_id: str
    started_at: Optional[str]
    ended_at: Optional[str]
    max_players: int
    winner_player: Optional[int]
    total_turns: int


class GameDetails(BaseModel):
    game_id: str
    started_at: Optional[str]
    ended_at: Optional[str]
    max_players: int
    winner_player: Optional[int]
    total_turns: int
    events: List[GameEvent]


class AnalysisRequest(BaseModel):
    question: str


class AnalysisResponse(BaseModel):
    game_id: str
    question: str
    analysis: str


# =========================
# Ciclo de vida (startup/shutdown)
# =========================

@app.on_event("startup")
async def startup_event():
    global db_pool
    db_pool = await asyncpg.create_pool(
        host='localhost',
        database='game_db',
        user='postgres',
        password='Sup3rSecret0',
        min_size=1,
        max_size=5
    )
    print("[analysis_api] DB pool creado")


@app.on_event("shutdown")
async def shutdown_event():
    global db_pool
    if db_pool:
        await db_pool.close()
        print("[analysis_api] DB pool cerrado")


# =========================
# Funciones auxiliares
# =========================

async def fetch_game_details(game_id: str) -> GameDetails:
    """
    Lee info básica de la partida + lista de eventos desde la DB.
    """
    if db_pool is None:
        raise RuntimeError("DB pool no inicializado")

    async with db_pool.acquire() as conn:
        game_row = await conn.fetchrow(
            """
            SELECT game_id, started_at, ended_at, max_players, winner_player, total_turns
            FROM games
            WHERE game_id = $1
            """,
            game_id,
        )

        if not game_row:
            raise HTTPException(status_code=404, detail="Game not found")

        event_rows = await conn.fetch(
            """
            SELECT ts, player_id, player_name, event_type, card, extra
            FROM game_events
            WHERE game_id = $1
            ORDER BY ts ASC
            """,
            game_id,
        )

    events: List[GameEvent] = []
    for r in event_rows:
        extra = r["extra"]
        if isinstance(extra, str):
            # por si extra está guardado como texto JSON
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {"raw": extra}
        events.append(
            GameEvent(
                ts=r["ts"].isoformat() if r["ts"] is not None else "",
                player_id=r["player_id"],
                player_name=r["player_name"],
                event_type=r["event_type"],
                card=r["card"],
                extra=extra,
            )
        )

    return GameDetails(
        game_id=game_row["game_id"],
        started_at=game_row["started_at"].isoformat() if game_row["started_at"] else None,
        ended_at=game_row["ended_at"].isoformat() if game_row["ended_at"] else None,
        max_players=game_row["max_players"],
        winner_player=game_row["winner_player"],
        total_turns=game_row["total_turns"] or 0,
        events=events,
    )


def build_prompt_from_game(game: GameDetails, question: str) -> str:
    """
    Construye un prompt de texto con toda la partida + la pregunta del usuario.
    """
    lines: List[str] = []

    lines.append("A continuación tienes la información de una partida de UNO.")
    lines.append("")
    lines.append("--- DATOS DE LA PARTIDA ---")
    lines.append(f"Partida: {game.game_id}")
    lines.append(f"Inicio: {game.started_at}")
    lines.append(f"Fin: {game.ended_at}")
    lines.append(f"Jugadores máximos: {game.max_players}")
    lines.append(f"Ganador (player_id relativo): {game.winner_player}")
    lines.append(f"Turnos registrados (aprox): {game.total_turns}")
    lines.append("")
    lines.append("Eventos de la partida (en orden cronológico):")

    for ev in game.events:
        base = f"- {ev.ts} | event={ev.event_type}"
        extras = []
        if ev.player_id is not None:
            extras.append(f"player_id={ev.player_id}")
        if ev.player_name:
            extras.append(f"name={ev.player_name}")
        if ev.card:
            extras.append(f"card={ev.card}")
        if extras:
            base += ", " + ", ".join(extras)
        lines.append(base)

    lines.append("")
    lines.append("--- FIN DATOS ---")
    lines.append("")
    lines.append("TAREA DEL MODELO:")
    lines.append(question.strip())

    return "\n".join(lines)


async def call_llm(prompt: str) -> str:
    """
    Llama al servidor vLLM (o compatible con OpenAI) de forma asíncrona.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Eres un analista experto en partidas de UNO. "
                        "Responde SIEMPRE en español, de forma clara, ordenada y breve. "
                        "Usa solamente la información de la partida que te doy como contexto."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.5,
            "max_tokens": 512,
            "stream": False,
        }
        headers = {"Content-Type": "application/json", "Authorization" : "Bearer EMPTY"}
        resp = await client.post(LLM_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"Error llamando al LLM: {resp.status_code} {resp.text}",
            )

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Respuesta inesperada del LLM: {e}")


async def save_analysis(game_id: str, question: str, analysis: str) -> None:
    """
    Guarda el análisis en la DB en una tabla simple game_analyses.
    Si aún no existe la tabla, deberías crearla con algo como:

    CREATE TABLE IF NOT EXISTS game_analyses (
        id          SERIAL PRIMARY KEY,
        game_id     TEXT NOT NULL,
        question    TEXT NOT NULL,
        analysis    TEXT NOT NULL,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );

    """
    if db_pool is None:
        raise RuntimeError("DB pool no inicializado")

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO game_analyses (game_id, question, analysis)
            VALUES ($1, $2, $3)
            """,
            game_id,
            question,
            analysis,
        )

# =========================
# Endpoints
# =========================



@app.get("/games/{game_id}", response_model=GameDetails)
async def get_game(game_id: str):
    """
    Devuelve la información básica de una partida + todos los eventos.
    """
    game = await fetch_game_details(game_id)
    return game


@app.post("/games/{game_id}/analysis", response_model=AnalysisResponse)
async def analyze_game(game_id: str, body: AnalysisRequest = Body(...)):
    """
    Realiza un NUEVO análisis sobre una partida ya jugada.
    - Lee la partida de la DB.
    - Construye prompt + pregunta.
    - Llama al LLM.
    - Guarda el análisis.
    - Devuelve el texto.
    """
    # 1. Cargar partida
    game = await fetch_game_details(game_id)

    # 2. Construir prompt
    prompt = build_prompt_from_game(game, body.question)

    # 3. Llamar al LLM
    analysis_text = await call_llm(prompt)

    try:
        await save_analysis(game_id, body.question, analysis_text)
    except Exception as e:
        print(f"[analysis_api] Error guardando análisis en DB: {e}")

    # 5. Responder
    return AnalysisResponse(
        game_id=game_id,
        question=body.question,
        analysis=analysis_text,
    )
@app.get("/games", response_model=List[GameSummary])
async def list_games(
    limit: int = Query(20, ge=1, le=200),
    only_finished: bool = Query(False, description="Si es true, solo partidas finalizadas"),
):
    """
    Lista partidas almacenadas en la base de datos.
    - Por defecto devuelve las últimas `limit` partidas ordenadas por inicio descendente.
    - Si `only_finished=true`, solo devuelve partidas con ended_at no nulo.
    """
    if db_pool is None:
        raise RuntimeError("DB pool no inicializado")

    where_clause = "WHERE ended_at IS NOT NULL" if only_finished else ""
    query = f"""
        SELECT game_id, started_at, ended_at, max_players, winner_player, total_turns
        FROM games
        {where_clause}
        ORDER BY started_at DESC
        LIMIT $1
    """

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, limit)

    summaries: List[GameSummary] = []
    for r in rows:
        summaries.append(
            GameSummary(
                game_id=r["game_id"],
                started_at=r["started_at"].isoformat() if r["started_at"] else None,
                ended_at=r["ended_at"].isoformat() if r["ended_at"] else None,
                max_players=r["max_players"],
                winner_player=r["winner_player"],
                total_turns=r["total_turns"] or 0,
            )
        )

    return summaries