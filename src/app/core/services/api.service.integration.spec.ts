import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ApiService } from './api.service';
describe('API y paginación', () => {
  let http: HttpTestingController;
  let api: ApiService;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    api = TestBed.inject(ApiService);
  });
  afterEach(() => http.verify());
  it('recorre páginas y conserva nulos y decimales', () => {
    let values: { valor: string | null }[] = [];
    api.all<{ valor: string | null }>('/datos/').subscribe((result) => (values = result));
    http
      .expectOne((r) => r.params.get('page') === '1')
      .flush({
        count: 2,
        next: 'https://untrusted.example/api/datos/?page=2',
        previous: null,
        results: [{ valor: '0.00' }],
      });
    http
      .expectOne((r) => r.url === api.base + '/datos/' && r.params.get('page') === '2')
      .flush({ count: 2, next: null, previous: '?page=1', results: [{ valor: null }] });
    expect(values).toEqual([{ valor: '0.00' }, { valor: null }]);
  });
  it('envía booleanos como true/false y omite filtros vacíos', () => {
    api.get('/datos/', { propios: true, leida: false, search: '', region: undefined }).subscribe();
    const r = http.expectOne((request) => request.url.endsWith('/datos/'));
    expect(r.request.params.toString()).toBe('propios=true&leida=false');
    r.flush({});
  });
  it('conserva el cuerpo de DELETE con versión', () => {
    api.delete('/portafolios/1/', { version: 7 }).subscribe();
    const r = http.expectOne(api.base + '/portafolios/1/');
    expect(r.request.method).toBe('DELETE');
    expect(r.request.body).toEqual({ version: 7 });
    r.flush(null, { status: 204, statusText: 'No Content' });
  });
});
