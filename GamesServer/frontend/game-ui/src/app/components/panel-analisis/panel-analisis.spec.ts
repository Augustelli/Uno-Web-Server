import { ComponentFixture, TestBed } from '@angular/core/testing';

import PanelAnalisis from './panel-analisis';

describe('PanelAnalisis', () => {
  let component: PanelAnalisis;
  let fixture: ComponentFixture<PanelAnalisis>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PanelAnalisis]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PanelAnalisis);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
