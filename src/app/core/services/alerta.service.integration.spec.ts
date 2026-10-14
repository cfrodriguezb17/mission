import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { AlertaService } from './alerta.service';
import { RealtimeService, RealtimeStatus, RealtimeUpdate } from './realtime.service';
import { NotifyService } from './notify.service';
import { signal } from '@angular/core';
import { Subject } from 'rxjs';
describe('Estado observable y polling de alertas', () => {
  let updates: Subject<RealtimeUpdate>;
  let statusChanges: Subject<RealtimeStatus>;
  let status: ReturnType<typeof signal<RealtimeStatus>>;
  let ended: Subject<void>;
  const notify = { show: vi.fn() };
  beforeEach(() => {
    vi.useFakeTimers();
    updates = new Subject();
    statusChanges = new Subject();
    ended = new Subject();
    status = signal<RealtimeStatus>('connecting');
    notify.show.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: RealtimeService,
          useValue: { updates$: updates, statusChanges$: statusChanges, ended$: ended, status },
        },
        { provide: NotifyService, useValue: notify },
      ],
    });
  });
  afterEach(() => {
    TestBed.inject(AlertaService).stop();
    TestBed.inject(HttpTestingController).verify();
    vi.useRealTimers();
  });
  it('actualiza cada 30 segundos y detiene el polling al salir', async () => {
    const api = TestBed.inject(AlertaService),
      http = TestBed.inject(HttpTestingController);
    let count: number | null = null;
    const listUpdated = vi.fn();
    api.updates$.subscribe(listUpdated);
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
    expect(listUpdated).toHaveBeenCalledTimes(1);
    api.stop();
    await vi.advanceTimersByTimeAsync(60000);
    http.expectNone((r) => r.url.endsWith('/alertas/resumen/'));
    expect(count).toBeNull();
  });
  it('continúa después de un error temporal', async () => {
    const api = TestBed.inject(AlertaService),
      http = TestBed.inject(HttpTestingController);
    api.start();
    await vi.advanceTimersByTimeAsync(0);
    http
      .expectOne((r) => r.url.endsWith('/alertas/resumen/'))
      .flush({}, { status: 503, statusText: 'Unavailable' });
    await vi.advanceTimersByTimeAsync(30000);
    http.expectOne((r) => r.url.endsWith('/alertas/resumen/')).flush({ total: 0, no_leidas: 0 });
  });
  it('en vivo actualiza el contador por avisos y deja de consultar cada 30 segundos', async () => {
    const api = TestBed.inject(AlertaService),
      http = TestBed.inject(HttpTestingController);
    api.start();
    http.expectOne((r) => r.url.endsWith('/alertas/resumen/')).flush({ total: 0, no_leidas: 0 });
    status.set('connected');
    statusChanges.next('connected');
    await vi.advanceTimersByTimeAsync(60000);
    http.expectNone((r) => r.url.endsWith('/alertas/resumen/'));
    updates.next({ alerts: true, dashboard: true, newAlerts: true });
    http.expectOne((r) => r.url.endsWith('/alertas/resumen/')).flush({ total: 1, no_leidas: 1 });
    expect(notify.show).toHaveBeenCalledTimes(1);
    let count = 0;
    api.summary$.subscribe((value) => {
      count = value?.no_leidas ?? 0;
    });
    expect(count).toBe(1);
    updates.next({ alerts: true, dashboard: true, newAlerts: false });
    http.expectOne((r) => r.url.endsWith('/alertas/resumen/')).flush({ total: 1, no_leidas: 1 });
    expect(notify.show).toHaveBeenCalledTimes(1);
  });
  it('restablece polling al desconectarse y cancela una consulta pendiente al terminar sesión', async () => {
    const api = TestBed.inject(AlertaService),
      http = TestBed.inject(HttpTestingController);
    api.start();
    http.expectOne((r) => r.url.endsWith('/alertas/resumen/')).flush({ no_leidas: 0 });
    statusChanges.next('connected');
    statusChanges.next('reconnecting');
    await vi.advanceTimersByTimeAsync(30000);
    const request = http.expectOne((r) => r.url.endsWith('/alertas/resumen/'));
    ended.next();
    expect(request.cancelled).toBe(true);
    await vi.advanceTimersByTimeAsync(60000);
    http.expectNone((r) => r.url.endsWith('/alertas/resumen/'));
  });
});
