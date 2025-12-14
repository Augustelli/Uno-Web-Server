import { Injectable, Inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  GameSummary,
  GameDetails,
  AnalysisRequest,
  AnalysisResponse,
} from '../models/uno-analytics.model';
import { environment } from '../../environments/environment';
@Injectable({
  providedIn: 'root',
})
export class UnoAnalytics {
  private readonly API_BASE_URL = environment.apiBaseUrl ?? '';
  constructor(private http: HttpClient) {}

  listGames(limit: number = 20, onlyFinished: boolean = false): Observable<GameSummary[]> {
    let params = new HttpParams()
      .set('limit', limit.toString())
      .set('only_finished', String(onlyFinished));
    return this.http.get<GameSummary[]>(`${this.API_BASE_URL}/games`, { params });
  }

  getGame(gameId: string): Observable<GameDetails> {
    return this.http.get<GameDetails>(`${this.API_BASE_URL}/games/${encodeURIComponent(gameId)}`);
  }

  analyzeGame(gameId: string, question: string): Observable<AnalysisResponse> {
    console.log("Realización de análisis para la partida:", gameId, "con la pregunta:", question);
    return this.http.post<AnalysisResponse>(
      `${this.API_BASE_URL}/games/${encodeURIComponent(gameId)}/analysis`,
      { question: question }
    );
  }
}
