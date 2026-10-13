import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { AlertService } from './alert.service';
describe('Estado observable y polling de alertas', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
  });
  afterEach(() => {
    TestBed.inject(AlertService).stop();
    TestBed.inject(HttpTestingController).verify();
    vi.useRealTimers();
  });
  it('actualiza cada 30 segundos y detiene el polling al salir', async () => {
    const api = TestBed.inject(AlertService),
      http = TestBed.inject(HttpTestingController);
    let count: number | null = null;
    api.summary$.subscribe((s) => (count = s?.no_leidas ?? null));
    api.start();
    await vi.advanceTimersByTimeAsync(0);
    http
      .expectOne((r) => r.url.endsWith('/alertas/resumen/'))
      .flush({ total: 4, no_leidas: 3, por_tipo: {}, por_severidad: {} });
    expect(count).toBe(3);
    await vi.advanceTimersByTimeAsync(30000);
    http
      .expectOne((r) => r.url.endsWith('/alertas/resumen/'))
      .flush({ total: 4, no_leidas: 2, por_tipo: {}, por_severidad: {} });
    expect(count).toBe(2);
    api.stop();
    await vi.advanceTimersByTimeAsync(60000);
    http.expectNone((r) => r.url.endsWith('/alertas/resumen/'));
    expect(count).toBeNull();
  });
  it('continúa después de un error temporal', async () => {
    const api = TestBed.inject(AlertService),
      http = TestBed.inject(HttpTestingController);
    api.start();
    await vi.advanceTimersByTimeAsync(0);
    http
      .expectOne((r) => r.url.endsWith('/alertas/resumen/'))
      .flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.advanceTimersByTimeAsync(30000);
    http.expectOne((r) => r.url.endsWith('/alertas/resumen/')).flush({ total: 0, no_leidas: 0 });
  });
});
