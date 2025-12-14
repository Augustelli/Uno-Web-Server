import { ComponentFixture, TestBed } from '@angular/core/testing';

import { GameDashboard } from './game-dashboard';

describe('GameDashboard', () => {
  let component: GameDashboard;
  let fixture: ComponentFixture<GameDashboard>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [GameDashboard]
    })
    .compileComponents();

    fixture = TestBed.createComponent(GameDashboard);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
