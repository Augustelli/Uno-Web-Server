import asyncio
from datetime import datetime
from typing import List, Optional
import os
import psycopg
import httpx
from fastapi import FastAPI, HTTPException, Query
from httpx import Request
from pydantic import BaseModel

from config import LOG_DB_DSN, N8N_ANALYSIS_URL, SERVER_PORT


# -------------------- Modelos -------------------- #

class GameSummary(BaseModel):
    game_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    max_players: int
    winner_player: Optional[int]
    total_turns: Optional[int]


class GameDetail(GameSummary):
    # Encapsula GameSummary para futuros campos extra si es necesario
    pass


class GameEvent(BaseModel):
    ts: datetime
    player_id: Optional[int]
    player_name: Optional[str]
    event_type: str
    card: Optional[str]
    extra: Optional[dict]


class AnalysisRequest(BaseModel):
    question: str


class AnalysisResponse(BaseModel):
    answer: str
    raw: dict  # respuesta cruda de n8n por si querés verla


# -------------------- Helpers de DB -------------------- #

def get_connection() -> psycopg.Connection:
    dsn = LOG_DB_DSN or os.getenv("LOG_DB_DSN")
    if not dsn:
        raise RuntimeError("LOG_DB_DSN no está configurado")
    return psycopg.connect(dsn)


# -------------------- FastAPI app -------------------- #

app = FastAPI(
    title="UNO Game Analytics API",
    description="API REST mínima para consultar partidas de UNO y pedir análisis a n8n.",
    version="1.0.0",
)


# -------------------- Endpoints -------------------- #

async def get_async_connection() -> "psycopg.AsyncConnection":
    dsn = LOG_DB_DSN or os.getenv("LOG_DB_DSN")
    if not dsn:
        raise RuntimeError("LOG_DB_DSN no está configurado")
    return await psycopg.AsyncConnection.connect(dsn)


@app.get("/games/{game_id}", response_model=GameDetail)
async def get_game(game_id: str):
    """
    Async detail lookup for a game.
    """
    conn = None
    try:
        conn = await get_async_connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT game_id, started_at, ended_at, max_players, winner_player, total_turns
                FROM games
                WHERE game_id = %s
                LIMIT 1;
                """,
                (game_id,),
            )
            row = await cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando la base de datos: {e}")
    finally:
        if conn:
            await conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Partida no encontrada")

    return GameDetail(
        game_id=row[0],
        started_at=row[1],
        ended_at=row[2],
        max_players=row[3],
        winner_player=row[4],
        total_turns=row[5],
    )


@app.get("/games/{game_id}/events", response_model=List[GameEvent])
async def get_game_events(game_id: str):
    """
    Async events list for a game (chronological).
    """
    conn = None
    try:
        conn = await get_async_connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT ts, player_id, player_name, event_type, card, extra
                FROM game_events
                WHERE game_id = %s
                ORDER BY ts ASC;
                """,
                (game_id,),
            )
            rows = await cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando la base de datos: {e}")
    finally:
        if conn:
            await conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="No se encontraron eventos para esa partida")

    events = [
        GameEvent(
            ts=r[0],
            player_id=r[1],
            player_name=r[2],
            event_type=r[3],
            card=r[4],
            extra=r[5],
        )
        for r in rows
    ]
    return events


async def call_n8n(client: httpx.AsyncClient, url: str, payload: dict):
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()

@app.post("/games/{game_id}/analyze", response_model=AnalysisResponse)
async def analyze_game(game_id: str, body: AnalysisRequest, request: Request):
    if not N8N_ANALYSIS_URL:
        raise HTTPException(status_code=500, detail="N8N_ANALYSIS_URL no está configurado")

    payload = {"game_id": game_id, "question": body.question}
    timeout_seconds = 60.0

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            call_task = asyncio.create_task(call_n8n(client, N8N_ANALYSIS_URL, payload))
            disconnect_task = asyncio.create_task(request.is_disconnected())

            done, pending = await asyncio.wait(
                {call_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout_seconds,
            )

            # client disconnected first
            if disconnect_task in done and disconnect_task.result():
                call_task.cancel()
                raise HTTPException(status_code=499, detail="Client disconnected")

            # timeout
            if not done:
                call_task.cancel()
                raise HTTPException(status_code=504, detail="Timeout calling n8n")

            # call finished
            result = call_task.result()

    except httpx.HTTPStatusError as e:
        # propagate n8n HTTP errors
        raise HTTPException(status_code=e.response.status_code, detail=f"n8n devolvió error: {e.response.text}")
    except asyncio.CancelledError:
        raise HTTPException(status_code=502, detail="Request cancelled")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error llamando a n8n: {e}")
    finally:
        # ensure pending tasks are cancelled
        for t in (call_task, disconnect_task):
            if not t.done():
                t.cancel()

    answer = result.get("answer") or str(result)
    return AnalysisResponse(answer=answer, raw=result)

# Endpoint de salud opcional
@app.get("/health")
def health_check():
    return {"status": "ok"}
