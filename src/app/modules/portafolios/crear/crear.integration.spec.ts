import { TestBed, ComponentFixture } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { PortfolioCreate } from './crear.component';
import { NotifyService } from '../../../core/services/notify.service';
import { environment } from '../../../../environments/environment';
import { portfolio } from '../../../testing/fixtures';

const base = environment.apiBaseUrl;
describe('Creación: formulario, servicio, HTTP y navegación', () => {
  let fixture: ComponentFixture<PortfolioCreate>;
  let http: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      imports: [PortfolioCreate],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: NotifyService, useValue: { show: vi.fn() } },
      ],
    });
    fixture = TestBed.createComponent(PortfolioCreate);
    http = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fixture.detectChanges();
  });
  afterEach(() => {
    try {
      http.verify();
    } finally {
      fixture.destroy();
      TestBed.resetTestingModule();
      vi.useRealTimers();
    }
  });
  async function validateName() {
    fixture.componentInstance.form.controls.nombre.setValue('  Estrategia Latam  ');
    await vi.advanceTimersByTimeAsync(350);
    const request = http.expectOne((r) => r.url.endsWith('/validar-nombre/'));
    expect(request.request.params.get('nombre')).toBe('Estrategia Latam');
    return request;
  }
  it('bloquea el botón y no envía un formulario inválido o con nombre pendiente', () => {
    const component = fixture.componentInstance;
    component.save();
    http.expectNone((r) => r.method === 'POST');
    component.form.controls.nombre.setValue('Nombre pendiente');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button[mat-flat-button]').disabled).toBe(true);
    component.save();
    http.expectNone((r) => r.method === 'POST');
  });
  it('envía el nombre recortado una sola vez y navega después del éxito', async () => {
    (await validateName()).flush({ disponible: true });
    const component = fixture.componentInstance;
    component.form.patchValue({ descripcion: 'Borrador', es_publico: true });
    component.save();
    component.save();
    const request = http.expectOne(base + '/portafolios/');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      nombre: 'Estrategia Latam',
      descripcion: 'Borrador',
      es_publico: true,
    });
    expect(navigate).not.toHaveBeenCalled();
    request.flush(portfolio());
    expect(navigate).toHaveBeenCalledWith(['/portafolios', 7]);
    expect(component.saving()).toBe(false);
  });
  it('un nombre duplicado bloquea creación incluso invocando save directamente', async () => {
    (await validateName()).flush({ disponible: false });
    fixture.componentInstance.save();
    expect(fixture.componentInstance.form.controls.nombre.hasError('duplicate')).toBe(true);
    http.expectNone((r) => r.method === 'POST');
  });
  it('conserva el borrador y muestra duplicado recibido al guardar después de validar', async () => {
    (await validateName()).flush({ disponible: true });
    const component = fixture.componentInstance;
    component.form.controls.descripcion.setValue('Conservar este texto');
    component.save();
    http
      .expectOne(base + '/portafolios/')
      .flush({ nombre: ['Este nombre ya existe.'] }, { status: 400, statusText: 'Bad Request' });
    fixture.detectChanges();
    expect(component.form.controls.nombre.getError('server')).toBe('Este nombre ya existe.');
    expect(fixture.nativeElement.textContent).toContain('Este nombre ya existe.');
    expect(component.form.controls.descripcion.value).toBe('Conservar este texto');
    expect(component.saving()).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });
});
