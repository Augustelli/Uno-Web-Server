import {ChangeDetectorRef, Component, Input} from '@angular/core';
import {UnoAnalytics} from '../../service/uno-analytics';
import {FormsModule} from '@angular/forms';
import {DatePipe, NgForOf, NgIf} from '@angular/common';
import {GameDetails} from '../../models/uno-analytics.model';

@Component({
  selector: 'app-panel-analisis',
  imports: [
    FormsModule,
    NgIf,
    DatePipe,
    NgForOf
  ],
  templateUrl: './panel-analisis.html',
  styleUrl: './panel-analisis.css',
})
class PanelAnalisis {
  @Input() game!: GameDetails;

  gameId!: string;
  question = '';
  analyzing = false;
  status = '';
  error = '';
  output: string | null = null;

  constructor(
    private api: UnoAnalytics,
    private cdr: ChangeDetectorRef
  ) {}

  runAnalysis() {
    this.error = '';
    this.status = '';
    this.output = null;
    this.gameId = this.game.game_id;
    const q = this.question.trim();
    if (!this.gameId) {
      this.error = 'No hay partida seleccionada.';
      return;
    }
    if (!q) {
      this.error = 'Escribe una pregunta para el modelo.';
      return;
    }

    this.analyzing = true;
    this.status = 'Analizando partida...';

    this.api.analyzeGame(this.gameId, q).subscribe({
      next: (res) => {
        console.log("Respuesta del análisis:", res);
        this.output = res.analysis || '(sin respuesta)';
        this.status = 'Análisis completado.';
        this.analyzing = false;
        this.cdr.detectChanges()
      },
      error: (err) => {
        console.error(err);
        this.error = 'Error llamando al endpoint de análisis.';
        this.status = '';
        this.analyzing = false;
        this.cdr.detectChanges()
      },
    });
  }
}

export default PanelAnalisis
