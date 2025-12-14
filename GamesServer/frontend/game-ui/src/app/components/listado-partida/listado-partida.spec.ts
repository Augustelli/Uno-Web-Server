import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ListadoPartida } from './listado-partida';

describe('ListadoPartida', () => {
  let component: ListadoPartida;
  let fixture: ComponentFixture<ListadoPartida>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ListadoPartida]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ListadoPartida);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
