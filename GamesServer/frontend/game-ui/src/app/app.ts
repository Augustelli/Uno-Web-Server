import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import {DashboardPrincipal} from './components/dashboard-principal/dashboard-principal';
import {PanelDetalle} from './components/panel-detalle/panel-detalle';
import {ListadoPartida} from './components/listado-partida/listado-partida';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, DashboardPrincipal, PanelDetalle, ListadoPartida],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  protected readonly title = signal('game-ui');
}
