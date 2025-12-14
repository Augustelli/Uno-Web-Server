import {Component, OnInit} from '@angular/core';
import {GameDetails, GameSummary} from '../../models/uno-analytics.model';
import {UnoAnalytics} from '../../service/uno-analytics';
import {CommonModule, DatePipe} from '@angular/common';
import {FormsModule} from '@angular/forms';

@Component({
  selector: 'app-game-dashboard',
  standalone: true,
  imports: [
    DatePipe,
    FormsModule,
    CommonModule
  ],
  templateUrl: './game-dashboard.html',
  styleUrl: './game-dashboard.css',
})
export class GameDashboard implements OnInit {
  games: GameSummary[] = [];
  gamesLoading = false;
  gamesError = '';
  gamesInfo = '';

  // filtros
  limit = 20;
  onlyFinished = false;

  // partida seleccionada
  selectedGame: GameDetails | null = null;
  detailsLoading = false;

  // análisis
  analysisQuestion = '';
  analysisOutput: string | null = null;
  analysisStatus = '';
  analysisError = '';
  analyzing = false;

  constructor(private api: UnoAnalytics) {}

  ngOnInit(): void {
    this.loadGames();
  }

  loadGames(): void {
    this.gamesLoading = true;
    this.gamesError = '';
    this.gamesInfo = 'Cargando partidas...';
    this.selectedGame = null;
    this.analysisOutput = null;
    this.analysisStatus = '';
    this.analysisError = '';

    const l = this.limit > 0 ? this.limit : 20;

    this.api.listGames(l, this.onlyFinished).subscribe({
      next: (games) => {
        this.games = games;
        this.gamesInfo = `${games.length} partida(s) cargada(s).`;
        this.gamesLoading = false;
      },
      error: (err) => {
        console.error(err);
        this.gamesError = 'Error cargando partidas';
        this.gamesInfo = '';
        this.gamesLoading = false;
      },
    });
  }

  selectGame(game: GameSummary): void {
    this.selectedGame = null;
    this.analysisOutput = null;
    this.analysisStatus = '';
    this.analysisError = '';
    this.detailsLoading = true;

    this.api.getGame(game.game_id).subscribe({
      next: (details) => {
        this.selectedGame = details;
        this.detailsLoading = false;
      },
      error: (err) => {
        console.error(err);
        this.analysisError = 'Error cargando detalles de la partida';
        this.detailsLoading = false;
      },
    });
  }

  isSelected(game: GameSummary): boolean {
    return this.selectedGame?.game_id === game.game_id;
  }

  runAnalysis(): void {
    this.analysisStatus = '';
    this.analysisError = '';
    this.analysisOutput = null;

    if (!this.selectedGame) {
      this.analysisError = 'Primero selecciona una partida.';
      return;
    }

    const q = this.analysisQuestion.trim();
    if (!q) {
      this.analysisError = 'Escribe una pregunta para el modelo.';
      return;
    }

    this.analyzing = true;
    this.analysisStatus = 'Analizando partida...';

    this.api.analyzeGame(this.selectedGame.game_id, q).subscribe({
      next: (res) => {
        this.analysisOutput = res.analysis || '(sin respuesta)';
        this.analysisStatus = 'Análisis completado.';
        this.analyzing = false;
      },
      error: (err) => {
        console.error(err);
        this.analysisError = 'Error llamando al modelo.';
        this.analysisStatus = '';
        this.analyzing = false;
      },
    });
  }
}
