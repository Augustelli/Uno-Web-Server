import {Component, Input, OnChanges, SimpleChanges} from '@angular/core';
import {GameDetails} from '../../models/uno-analytics.model';
import {DatePipe, NgClass, NgForOf, NgIf} from '@angular/common';

@Component({
  selector: 'app-panel-detalle',
  imports: [
    DatePipe,
    NgClass,
    NgIf,
    NgForOf
  ],
  templateUrl: './panel-detalle.html',
  styleUrl: './panel-detalle.css',
})
export class PanelDetalle implements OnChanges {
  @Input() game: GameDetails | null = null;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['game']) {
      console.log('PanelDetalle received game:', this.game);
      console.log('PanelDetalle game DTO (pretty):', JSON.stringify(this.game, null, 2));
    }
  }
}
