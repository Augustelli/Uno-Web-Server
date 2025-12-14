import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DashboardPrincipal } from './dashboard-principal';

describe('DashboardPrincipal', () => {
  let component: DashboardPrincipal;
  let fixture: ComponentFixture<DashboardPrincipal>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DashboardPrincipal]
    })
    .compileComponents();

    fixture = TestBed.createComponent(DashboardPrincipal);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
