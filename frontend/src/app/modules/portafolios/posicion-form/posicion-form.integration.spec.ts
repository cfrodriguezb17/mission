import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { PositionDialog } from './posicion-form.component';
import { environment } from '../../../../environments/environment';
import { country, portfolio, position, risk } from '../../../testing/fixtures';

const base = environment.apiBaseUrl;
describe('Posiciones: formulario, API y conflictos de versión', () => {
  let component: PositionDialog;
  let http: HttpTestingController;
  let close: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    close = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: MAT_DIALOG_DATA,
          useValue: {
            portfolio: portfolio(),
            countries: [
              country(),
              country({ codigo_iso: 'BR', nombre: 'Brasil', moneda_codigo: 'BRL' }),
            ],
          },
        },
        { provide: MatDialogRef, useValue: { close } },
      ],
    });
    component = TestBed.runInInjectionContext(() => new PositionDialog());
    http = TestBed.inject(HttpTestingController);
    http
      .expectOne((r) => r.url.endsWith('/riesgo/'))
      .flush({
        count: 2,
        next: null,
        previous: null,
        results: [risk(), risk({ id: 2, pais: 'BR', indice_compuesto: '20.00' })],
      });
    component.form.patchValue({
      pais: 'CO',
      tipo_activo: 'RENTA_FIJA',
      monto_inversion_usd: '1,234.56',
      fecha_entrada: '2020-01-01',
      notas: 'Borrador local',
    });
  });
  afterEach(() => {
    try {
      http.verify();
    } finally {
      TestBed.resetTestingModule();
    }
  });
  function conflict() {
    component.save();
    http
      .expectOne(base + '/portafolios/7/posiciones/')
      .flush({}, { status: 409, statusText: 'Conflict' });
    expect(component.conflict()).toBe(true);
    expect(close).not.toHaveBeenCalled();
    return http.expectOne(base + '/portafolios/7/');
  }
  it('envía centavos sin separadores, versión actual y evita doble envío', () => {
    component.save();
    component.save();
    const request = http.expectOne(base + '/portafolios/7/posiciones/');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      version: 3,
      pais: 'CO',
      tipo_activo: 'RENTA_FIJA',
      monto_inversion_usd: '1234.56',
      fecha_entrada: '2020-01-01',
      fecha_salida: null,
      notas: 'Borrador local',
    });
    request.flush(position({ version_portafolio: 4 }));
    expect(close).toHaveBeenCalledExactlyOnceWith(true);
    expect(component.saving()).toBe(false);
  });
  it('no envía una fecha imposible a la API', () => {
    component.form.controls.fecha_entrada.setValue('2025-02-29');
    component.save();
    expect(component.form.controls.fecha_entrada.hasError('date')).toBe(true);
    http.expectNone((r) => r.method === 'POST');
  });
  it('conserva el borrador en 409 y solo reintenta con versión nueva tras revisión', () => {
    conflict().flush(portfolio({ version: 4 }));
    expect(component.form.controls.notas.value).toBe('Borrador local');
    expect(component.form.controls.monto_inversion_usd.value).toBe('1,234.56');
    component.save();
    http.expectNone((r) => r.method === 'POST');
    component.conflict.set(false); // La acción explícita «Revisé los cambios».
    component.save();
    const retry = http.expectOne(base + '/portafolios/7/posiciones/');
    expect(retry.request.body.version).toBe(4);
    retry.flush(position());
    expect(close).toHaveBeenCalledWith(true);
  });
  it('revalida límites contra las posiciones recibidas después del conflicto', () => {
    conflict().flush(portfolio({ version: 4, posiciones: [position(), position({ id: 2 })] }));
    component.conflict.set(false);
    component.save();
    expect(component.form.getError('cross')).toContain('dos posiciones');
    http.expectNone((r) => r.method === 'POST');
  });
  it('mantiene el conflicto y borrador si falla la recarga, sin reenviar automáticamente', () => {
    conflict().flush({}, { status: 503, statusText: 'Unavailable' });
    expect(component.reloadFailed()).toBe(true);
    expect(component.conflict()).toBe(true);
    expect(component.error()).toContain('No se pudo recargar');
    component.save();
    http.expectNone((r) => r.method === 'POST');
    expect(component.form.controls.notas.value).toBe('Borrador local');
  });
  it('no guarda si la recarga informa que se perdió el permiso de edición', () => {
    conflict().flush(portfolio({ version: 4, puede_editar: false }));
    component.conflict.set(false);
    component.save();
    http.expectNone((r) => r.method === 'POST');
  });
  it('previsualiza cambios de país y monto sin nuevas peticiones ni escrituras', () => {
    component.current.set(portfolio({ posiciones: [position()] }));
    component.form.patchValue({ pais: 'BR', monto_inversion_usd: '3,000.00' });
    expect(component.preview()).toMatchObject({
      total_invertido_usd: '4000.00',
      riesgo_promedio_ponderado: '35.00',
    });
    component.form.controls.monto_inversion_usd.setValue('2000.00');
    expect(component.preview()).toMatchObject({
      total_invertido_usd: '3000.00',
      riesgo_promedio_ponderado: '40.00',
    });
    component.form.controls.pais.setValue('CO');
    expect(component.preview()?.riesgo_promedio_ponderado).toBe('80.00');
    http.expectNone(() => true);
    expect(close).not.toHaveBeenCalled();
  });
  it('no conserva cifras del borrador anterior cuando el país o monto dejan de ser válidos', () => {
    expect(component.preview()).not.toBeNull();
    component.form.controls.pais.setValue('Colombia cualquiera');
    expect(component.preview()).toBeNull();
    component.form.patchValue({ pais: 'CO', monto_inversion_usd: '999.99' });
    expect(component.preview()).toBeNull();
    http.expectNone(() => true);
  });
  it('recarga índices solo al reintentar y conserva el monto durante un fallo de red', () => {
    component.loadRisks();
    const request = http.expectOne((r) => r.url.endsWith('/riesgo/'));
    expect(component.risksLoading()).toBe(true);
    component.loadRisks();
    http.expectNone((r) => r.url.endsWith('/riesgo/'));
    request.flush({}, { status: 503, statusText: 'Unavailable' });
    expect(component.risksError()).toBe(true);
    expect(component.preview()?.total_invertido_usd).toBe('1234.56');
    expect(component.form.controls.monto_inversion_usd.value).toBe('1,234.56');
    component.loadRisks();
    http
      .expectOne((r) => r.url.endsWith('/riesgo/'))
      .flush({
        count: 1,
        next: null,
        previous: null,
        results: [risk({ indice_compuesto: '70.00' })],
      });
    expect(component.risksError()).toBe(false);
    expect(component.risksLoading()).toBe(false);
    expect(component.preview()?.riesgo_promedio_ponderado).toBe('70.00');
  });
  it('actualiza la estimación con las posiciones recargadas por un conflicto', () => {
    component.form.controls.monto_inversion_usd.setValue('1000.00');
    conflict().flush(
      portfolio({
        version: 4,
        posiciones: [position({ id: 2, pais: 'BR', monto_inversion_usd: '3000.00' })],
      }),
    );
    expect(component.preview()).toMatchObject({
      total_invertido_usd: '4000.00',
      riesgo_promedio_ponderado: '35.00',
    });
    expect(component.form.controls.notas.value).toBe('Borrador local');
    http.expectNone(() => true);
  });
  it('cancela una consulta pendiente al destruir el formulario', () => {
    component.loadRisks();
    const request = http.expectOne((r) => r.url.endsWith('/riesgo/'));
    TestBed.resetTestingModule();
    expect(request.cancelled).toBe(true);
  });
});
