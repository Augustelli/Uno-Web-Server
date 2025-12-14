import { TestBed } from '@angular/core/testing';

import { UnoAnalytics } from './uno-analytics';

describe('UnoAnalytics', () => {
  let service: UnoAnalytics;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(UnoAnalytics);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
