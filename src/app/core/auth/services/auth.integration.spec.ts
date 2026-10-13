import { TestBed } from '@angular/core/testing';
import { provideHttpClient, withInterceptors, HttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { provideRouter, Router } from '@angular/router';
import { AuthService } from './auth.service';
import { jwtInterceptor } from '../interceptors/jwt.interceptor';
import { loadingInterceptor } from '../../interceptors/loading.interceptor';
import { errorInterceptor } from '../../interceptors/error.interceptor';
import { NotifyService } from '../../services/notify.service';
import { LoadingService } from '../../services/loading.service';
import { environment } from '../../../../environments/environment';
const base = environment.apiBaseUrl;
const user = {
  id: 1,
  email: 'test@example.com',
  nombre_completo: 'Analista',
  rol: 'ANALISTA',
  activo: true,
};
describe('Sesión e interceptores integrados', () => {
  let http: HttpTestingController;
  let auth: AuthService;
  let client: HttpClient;
  const notify = { show: vi.fn() };
  beforeEach(() => {
    localStorage.clear();
    notify.show.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, jwtInterceptor])),
        provideHttpClientTesting(),
        { provide: NotifyService, useValue: notify },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
    client = TestBed.inject(HttpClient);
  });
  afterEach(() => {
    try {
      http.verify();
    } finally {
      localStorage.clear();
      TestBed.resetTestingModule();
    }
  });
  it('guarda tokens y consulta el perfil antes de completar el login', () => {
    let done = false;
    auth.login('test@example.com', 'secret').subscribe(() => (done = true));
    const login = http.expectOne(base + '/auth/login/');
    expect(login.request.headers.has('Authorization')).toBe(false);
    login.flush({ access: 'token', refresh: 'refresh' });
    const profile = http.expectOne(base + '/auth/me/');
    expect(profile.request.headers.get('Authorization')).toBe('Bearer token');
    expect(done).toBe(false);
    profile.flush(user);
    expect(auth.user()?.rol).toBe('ANALISTA');
    expect(localStorage.getItem('datapulse.refresh')).toBe('refresh');
    expect(done).toBe(true);
  });
  it('renueva una sola vez cuando dos solicitudes reciben 401', () => {
    localStorage.setItem('datapulse.access', 'old');
    localStorage.setItem('datapulse.refresh', 'refresh');
    client.get(base + '/a/').subscribe();
    client.get(base + '/b/').subscribe();
    http.expectOne(base + '/a/').flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne(base + '/b/').flush({}, { status: 401, statusText: 'Unauthorized' });
    const renewal = http.expectOne(base + '/auth/refresh/');
    renewal.flush({ access: 'new' });
    const retries = http.match((r) => r.url === base + '/a/' || r.url === base + '/b/');
    expect(retries).toHaveLength(2);
    for (const r of retries) {
      expect(r.request.headers.get('Authorization')).toBe('Bearer new');
      r.flush({});
    }
  });
  it('cierra sesión si el refresh también expira, sin bucle', () => {
    localStorage.setItem('datapulse.access', 'old');
    localStorage.setItem('datapulse.refresh', 'expired');
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    client.get(base + '/a/').subscribe({ error: () => {} });
    http.expectOne(base + '/a/').flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne(base + '/auth/refresh/').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.access).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/login']);
    expect(notify.show).toHaveBeenCalledTimes(1);
  });
  it('no adjunta credenciales a otro origen', () => {
    localStorage.setItem('datapulse.access', 'secret');
    client.get('https://example.com/image').subscribe();
    const r = http.expectOne('https://example.com/image');
    expect(r.request.headers.has('Authorization')).toBe(false);
    r.flush({});
  });
  it('mantiene la carga hasta que terminan todas las solicitudes', () => {
    const loading = TestBed.inject(LoadingService);
    client.get(base + '/a/').subscribe();
    client.get(base + '/b/').subscribe({ error: () => {} });
    expect(loading.active()).toBe(true);
    http.expectOne(base + '/a/').flush({});
    expect(loading.active()).toBe(true);
    http.expectOne(base + '/b/').flush({}, { status: 500, statusText: 'Error' });
    expect(loading.active()).toBe(false);
  });
  it('RGR sesión: una renovación tardía no restaura credenciales tras logout', () => {
    localStorage.setItem('datapulse.access', 'old');
    localStorage.setItem('datapulse.refresh', 'refresh');
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const values: unknown[] = [];
    client.get(base + '/a/').subscribe({ next: (value) => values.push(value), error: () => {} });
    http.expectOne(base + '/a/').flush({}, { status: 401, statusText: 'Unauthorized' });
    const renewal = http.expectOne(base + '/auth/refresh/');
    auth.logout();
    // A real server may finish even after the client cancels the request.
    if (!renewal.cancelled) renewal.flush({ access: 'late-access' });
    const retries = http.match(base + '/a/');
    for (const retry of retries) retry.flush({});
    expect(retries).toHaveLength(0);
    expect(auth.access).toBeNull();
    expect(auth.refreshToken).toBeNull();
    expect(values).toEqual([]);
    expect(TestBed.inject(LoadingService).active()).toBe(false);
    http.expectNone(base + '/a/');
  });
  it('RGR sesión: un perfil tardío no recupera el usuario después de logout', () => {
    localStorage.setItem('datapulse.access', 'token');
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    auth.loadProfile().subscribe();
    const profile = http.expectOne(base + '/auth/me/');
    auth.logout();
    if (!profile.cancelled) profile.flush(user);
    expect(auth.user()).toBeNull();
    expect(auth.canWrite()).toBe(false);
  });

  it('un 401 tardío del token anterior usa el token ya renovado sin otro refresh', () => {
    localStorage.setItem('datapulse.access', 'old');
    localStorage.setItem('datapulse.refresh', 'refresh');
    client.get(base + '/a/').subscribe();
    client.get(base + '/b/').subscribe();
    const a = http.expectOne(base + '/a/');
    const b = http.expectOne(base + '/b/');
    a.flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne(base + '/auth/refresh/').flush({ access: 'new' });
    http.expectOne(base + '/a/').flush({});
    b.flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectNone(base + '/auth/refresh/');
    const retry = http.expectOne(base + '/b/');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer new');
    retry.flush({});
  });
  it('un 403 conserva la sesión y no intenta renovar', () => {
    localStorage.setItem('datapulse.access', 'valid');
    localStorage.setItem('datapulse.refresh', 'refresh');
    client.get(base + '/admin/').subscribe({ error: () => {} });
    http
      .expectOne(base + '/admin/')
      .flush(
        { error: { mensaje: 'No tienes permiso.' } },
        { status: 403, statusText: 'Forbidden' },
      );
    http.expectNone(base + '/auth/refresh/');
    expect(auth.access).toBe('valid');
    expect(notify.show).toHaveBeenCalledWith('No tienes permiso.');
  });
  it('muestra el plazo Retry-After ante 429 y termina la carga', () => {
    client.get(base + '/a/').subscribe({ error: () => {} });
    http
      .expectOne(base + '/a/')
      .flush(
        {},
        { status: 429, statusText: 'Too Many Requests', headers: { 'Retry-After': '12' } },
      );
    expect(notify.show).toHaveBeenCalledWith(
      'Demasiadas solicitudes. Intenta de nuevo en 12 segundos.',
    );
    expect(TestBed.inject(LoadingService).active()).toBe(false);
  });
  it('logout cancela un login pendiente y no permite guardar sus tokens', () => {
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    auth.login('test@example.com', 'secret').subscribe();
    const login = http.expectOne(base + '/auth/login/');
    auth.logout();
    expect(login.cancelled).toBe(true);
    expect(auth.access).toBeNull();
    http.expectNone(base + '/auth/me/');
  });
  it('cancelar la última suscripción de refresh permite iniciar otra renovación', () => {
    localStorage.setItem('datapulse.refresh', 'refresh');
    const subscription = auth.renew().subscribe();
    const first = http.expectOne(base + '/auth/refresh/');
    subscription.unsubscribe();
    expect(first.cancelled).toBe(true);
    let result = '';
    auth.renew().subscribe((access) => (result = access));
    http.expectOne(base + '/auth/refresh/').flush({ access: 'new' });
    expect(result).toBe('new');
  });
});
