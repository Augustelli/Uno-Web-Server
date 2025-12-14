import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PanelDetalle } from './panel-detalle';

describe('PanelDetalle', () => {
  let component: PanelDetalle;
  let fixture: ComponentFixture<PanelDetalle>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PanelDetalle]
    })
    .compileComponents();

    fixture = TestBed.createComponent(PanelDetalle);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
