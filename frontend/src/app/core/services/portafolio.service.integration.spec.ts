import { TestBed } from '@angular/core/testing';
import { FormControl } from '@angular/forms';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { PortafolioService } from './portafolio.service';
describe('Disponibilidad asíncrona de nombres', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
  });
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
    vi.useRealTimers();
  });
  it('espera y cancela respuestas del nombre anterior al escribir', async () => {
    const api = TestBed.inject(PortafolioService),
      http = TestBed.inject(HttpTestingController);
    const control = new FormControl('Nombre anterior', { asyncValidators: api.nameValidator(8) });
    await vi.advanceTimersByTimeAsync(349);
    http.expectNone((r) => r.url.includes('validar-nombre'));
    await vi.advanceTimersByTimeAsync(1);
    const old = http.expectOne((r) => r.params.get('nombre') === 'Nombre anterior');
    expect(old.request.params.get('excluir')).toBe('8');
    control.setValue('Nombre nuevo');
    expect(old.cancelled).toBe(true);
    await vi.advanceTimersByTimeAsync(350);
    http.expectOne((r) => r.params.get('nombre') === 'Nombre nuevo').flush({ disponible: false });
    expect(control.errors).toEqual({ duplicate: true });
  });
  it('un fallo de red nunca se interpreta como disponible', async () => {
    const api = TestBed.inject(PortafolioService),
      http = TestBed.inject(HttpTestingController);
    const control = new FormControl('Latam', { asyncValidators: api.nameValidator() });
    await vi.advanceTimersByTimeAsync(350);
    http.expectOne((r) => r.url.includes('validar-nombre')).error(new ProgressEvent('error'));
    expect(control.errors).toEqual({ availability: true });
  });
});
