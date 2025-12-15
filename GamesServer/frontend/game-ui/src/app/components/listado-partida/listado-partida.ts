import {Component, EventEmitter, Input, Output} from '@angular/core';
import {GameSummary} from '../../models/uno-analytics.model';
import {DatePipe, NgClass, NgForOf, NgIf} from '@angular/common';
import {FormsModule} from '@angular/forms';

@Component({
  selector: 'app-listado-partida',
  imports: [
    NgClass,
    FormsModule,
    DatePipe,
    NgIf,
    NgForOf
  ],
  templateUrl: './listado-partida.html',
  styleUrl: './listado-partida.css',
})
export class ListadoPartida {
  @Input() games: GameSummary[] = [];
  @Input() loading = false;
  @Input() error = '';
  @Input() limit = 0;
  @Input() onlyFinished = false;
  @Input() selectedGameId: string | null = null;

  @Output() limitChange = new EventEmitter<number>();
  @Output() onlyFinishedChange = new EventEmitter<boolean>();
  @Output() refreshRequested = new EventEmitter<void>();
  @Output() gameSelected = new EventEmitter<string>();

  searchText = '';

  onLimitInput(v: string) {
    const n = parseInt(v, 10);
    this.limitChange.emit(Number.isFinite(n) && n >= 0 ? n : 20);
  }

  onOnlyFinishedToggle(v: boolean) {
    this.onlyFinishedChange.emit(v);
  }

  onRefresh() {
    this.refreshRequested.emit();
  }

  selectGame(id: string) {
    this.gameSelected.emit(id);
  }

  isSelected(game: GameSummary): boolean {
    return this.selectedGameId === game.game_id;
  }
}
