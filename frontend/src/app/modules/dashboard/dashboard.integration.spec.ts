import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { Dashboard } from './dashboard.component';
import { AuthService } from '../../core/auth/services/auth.service';
import { NotifyService } from '../../core/services/notify.service';
import { Role, User } from '../../core/models/api.models';
import { country } from '../../testing/fixtures';
import { Subject } from 'rxjs';
import { RealtimeService, RealtimeUpdate } from '../../core/services/realtime.service';
import { SILENT } from '../../core/services/api.service';

const envelope = (results: unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});
describe('Dashboard: datos, filtros, cancelación y administración', () => {
  let http: HttpTestingController;
  let component: Dashboard;
  let updates: Subject<RealtimeUpdate>;
  const user = signal<User | null>(null);
  beforeEach(() => {
    updates = new Subject();
    user.set({
      id: 1,
      email: 'admin@example.com',
      nombre_completo: 'Admin',
      rol: 'ADMIN',
      activo: true,
    });
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { user } },
        { provide: NotifyService, useValue: { show: vi.fn() } },
        { provide: RealtimeService, useValue: { updates$: updates } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    component = TestBed.runInInjectionContext(() => new Dashboard());
  });
  afterEach(() => {
    try {
      http.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });
  function flushOverview() {
    http
      .expectOne((r) => r.url.endsWith('/dashboard/resumen/'))
      .flush({
        total_paises: 1,
        alertas_activas: 2,
        portafolios_usuario: 3,
        promedio_irpc: null,
        paises_con_datos_parciales: 1,
      });
    http.expectOne((r) => r.url.endsWith('/paises/')).flush(envelope([country()]));
    http.expectOne((r) => r.url.endsWith('/riesgo/')).flush(envelope([]));
    http.expectOne((r) => r.url.endsWith('/dashboard/mapa/')).flush(envelope([]));
  }
  function trends() {
    return http.expectOne((r) => r.url.endsWith('/dashboard/tendencias/'));
  }
  function emptyTrends() {
    trends().flush({
      ...envelope([]),
      tipo: 'PIB',
      unidad: 'USD',
      anio_inicio: 2021,
      anio_fin: 2025,
    });
  }
  it('mantiene null como ausencia de datos y conserva años y evidencia simulada', () => {
    flushOverview();
    trends().flush({
      ...envelope([
        {
          pais: 'CO',
          nombre_pais: 'Colombia',
          datos_parciales: true,
          valores: [
            { anio: 2024, valor: null, fuente: null, es_simulado: null },
            { anio: 2025, valor: '0.00', fuente: 'Prueba', es_simulado: true },
          ],
        },
      ]),
      tipo: 'PIB',
      unidad: 'USD',
      anio_inicio: 2021,
      anio_fin: 2025,
    });
    expect(component.summary()?.promedio_irpc).toBeNull();
    expect(component.trendSeries()).toEqual([{ label: 'Colombia', values: [null, 0] }]);
    expect(component.trendLabels()).toEqual(['2024', '2025']);
    expect(component.trendNotice()).toBe(true);
    expect(component.loading()).toBe(false);
  });
  it('cancela el indicador anterior y consulta solo el nuevo conjunto de países', () => {
    flushOverview();
    const old = trends();
    component.filters.setValue({ tipo: 'INFLACION', paises: ['CO', 'MX'] });
    expect(old.cancelled).toBe(true);
    const current = trends();
    expect(current.request.params.get('tipo')).toBe('INFLACION');
    expect(current.request.params.get('paises')).toBe('CO,MX');
    current.flush({
      ...envelope([]),
      tipo: 'INFLACION',
      unidad: '%',
      anio_inicio: 2021,
      anio_fin: 2025,
    });
    component.filters.controls.paises.setValue(['CO', 'MX', 'BR', 'EC']);
    http.expectNone((r) => r.url.endsWith('/dashboard/tendencias/'));
    expect(component.filters.invalid).toBe(true);
  });
  it('un 503 de sincronización conserva los datos que ya se estaban mostrando', () => {
    flushOverview();
    emptyTrends();
    const previous = component.summary();
    component.runJob('sync');
    component.runJob('sync');
    const job = http.expectOne((r) => r.url.endsWith('/paises/sync-indicadores/'));
    expect(job.request.method).toBe('POST');
    job.flush({}, { status: 503, statusText: 'Unavailable' });
    expect(component.summary()).toBe(previous);
    expect(component.jobMessage()).toContain('datos guardados');
    expect(component.busy()).toBe(false);
  });
  it.each<Role>(['ANALISTA', 'VIEWER'])(
    'el rol %s no puede iniciar tareas administrativas',
    (rol) => {
      flushOverview();
      emptyTrends();
      user.update((current) => current && { ...current, rol });
      component.runJob('sync');
      component.runJob('risk');
      http.expectNone((r) => r.method === 'POST');
    },
  );
  it('actualiza datos en segundo plano sin ocultar el dashboard ni cambiar sus filtros', () => {
    flushOverview();
    emptyTrends();
    component.filters.setValue({ tipo: 'INFLACION', paises: ['CO'] });
    emptyTrends();
    updates.next({ alerts: false, dashboard: true, newAlerts: false });
    expect(component.loading()).toBe(false);
    const summary = http.expectOne((r) => r.url.endsWith('/dashboard/resumen/'));
    expect(summary.request.context.get(SILENT)).toBe(true);
    summary.flush({ total_paises: 2, alertas_activas: 4, promedio_irpc: '24.00' });
    http.expectOne((r) => r.url.endsWith('/paises/')).flush(envelope([country()]));
    http.expectOne((r) => r.url.endsWith('/riesgo/')).flush(envelope([]));
    http.expectOne((r) => r.url.endsWith('/dashboard/mapa/')).flush(envelope([]));
    const trend = trends();
    expect(trend.request.context.get(SILENT)).toBe(true);
    expect(trend.request.params.get('tipo')).toBe('INFLACION');
    expect(trend.request.params.get('paises')).toBe('CO');
    trend.flush({ ...envelope([]), tipo: 'INFLACION' });
    expect(component.summary()?.alertas_activas).toBe(4);
    expect(component.filters.getRawValue()).toEqual({ tipo: 'INFLACION', paises: ['CO'] });
  });
  it('un fallo de actualización automática conserva la información visible', () => {
    flushOverview();
    emptyTrends();
    const previous = component.summary();
    updates.next({ alerts: false, dashboard: true, newAlerts: false });
    const requests = http.match((r) => !r.url.endsWith('/dashboard/tendencias/'));
    requests
      .find((r) => r.request.url.endsWith('/dashboard/resumen/'))!
      .flush({}, { status: 503, statusText: 'Unavailable' });
    emptyTrends();
    expect(component.summary()).toBe(previous);
    expect(component.error()).toBe(false);
    expect(component.loading()).toBe(false);
  });
});
