import {ChangeDetectorRef, Component, OnInit} from '@angular/core';
import {GameDetails, GameSummary} from '../../models/uno-analytics.model';
import {UnoAnalytics} from '../../service/uno-analytics';
import {ListadoPartida} from '../listado-partida/listado-partida';
import {PanelDetalle} from '../panel-detalle/panel-detalle';
import PanelAnalisis from '../panel-analisis/panel-analisis';
import {NgIf} from '@angular/common';

@Component({
  selector: 'app-dashboard-principal',
  imports: [
    ListadoPartida,
    PanelDetalle,
    PanelAnalisis,
    NgIf
  ],
  templateUrl: './dashboard-principal.html',
  styleUrl: './dashboard-principal.css',
})
export class DashboardPrincipal implements OnInit{
  games: GameSummary[] = [];
  gamesLoading = false;
  loading = false;
  error: string = "";
  gamesError = '';

  limit = 20;
  onlyFinished = false;

  selectedGameId: string | null = null;
  selectedGame: GameDetails | null = null;
  detailsLoading = false;
  detailsError = '';

  constructor(
    private api: UnoAnalytics,
    private cd: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    this.loadGames();
  }

  loadGames(): void {
    this.loading = true;
    this.error = '';
    this.api.listGames(this.limit, this.onlyFinished).subscribe({
      next: (res) => {
        console.log('Backend games payload:', res);
        this.games = Array.isArray(res) ? [...res] : [];
        this.loading = false;
        this.gamesLoading = false;
        this.cd.markForCheck();
      },
      error: (err) => {
        console.error('Failed loading games:', err);
        this.error = err?.message ?? 'Failed to load games';
        this.loading = false;
        this.gamesLoading = false;
        this.cd.markForCheck();
      },
    });
  }

  onGameSelected(id: string): void {
    this.selectedGameId = id;
    this.selectedGame = null;
    this.detailsLoading = true;
    this.detailsError = '';

    this.api.getGame(id).subscribe({
      next: (detail) => {
        console.log('getGame response (GameDetails):', detail);
        console.log('getGame DTO (pretty):', JSON.stringify(detail, null, 2));
        this.selectedGame = detail;
        this.detailsLoading = false;
        this.cd.markForCheck();
      },
      error: (err) => {
        console.error('Failed loading game details:', err);
        this.detailsError = err?.message ?? 'Failed to load game details';
        this.detailsLoading = false;
        this.cd.markForCheck();
      },
    });
  }

    onLimitChange(n: number) {
    this.limit = n;
    this.loadGames();
  }

  onOnlyFinishedChange(v: boolean) {
    this.onlyFinished = v;
    this.loadGames();
  }

  onRefreshRequested() {
    this.loadGames();
    if (this.selectedGameId) {
      this.onGameSelected(this.selectedGameId);
    }
  }
}
