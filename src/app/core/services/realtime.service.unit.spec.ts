import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import { of, Subject, tap } from 'rxjs';
import { AuthService } from '../auth/services/auth.service';
import { ApiService } from './api.service';
import { NotifyService } from './notify.service';
import {
  RealtimeService,
  RealtimeEvent,
  RealtimeUpdate,
  SOCKET_FACTORY,
  socketUrl,
} from './realtime.service';

class Socket {
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  readonly close = vi.fn();
  message(value: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(value) }));
  }
  end(code = 1006) {
    this.onclose?.(new CloseEvent('close', { code }));
  }
}
const user = {
  id: 1,
  email: 'user@example.com',
  nombre_completo: 'User',
  rol: 'ANALISTA',
  activo: true,
};

describe('WebSocket: sesión, reconexión y avisos', () => {
  let realtime: RealtimeService;
  let sockets: Socket[];
  let changed: Subject<string | null>;
  let renewal: Subject<string>;
  let auth: {
    access: string | null;
    refreshToken: string | null;
    user: ReturnType<typeof signal<typeof user | null>>;
    accessChanges$: Subject<string | null>;
    renew: ReturnType<typeof vi.fn>;
    loadProfile: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn<() => void>>;
  };
  const create = vi.fn();
  const notify = { show: vi.fn() };
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0);
    sockets = [];
    changed = new Subject();
    renewal = new Subject();
    auth = {
      access: 'access-A',
      refreshToken: 'refresh',
      user: signal(user),
      accessChanges$: changed,
      renew: vi.fn(() =>
        renewal.pipe(
          tap((access) => {
            auth.access = access;
            changed.next(access);
          }),
        ),
      ),
      loadProfile: vi.fn(() => of(user)),
      logout: vi.fn(() => {
        auth.access = null;
        auth.user.set(null);
        changed.next(null);
      }),
    };
    create.mockReset().mockImplementation(() => {
      const socket = new Socket();
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });
    notify.show.mockClear();
    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: auth },
        { provide: ApiService, useValue: { base: 'http://127.0.0.1:8000/api' } },
        { provide: NotifyService, useValue: notify },
        { provide: SOCKET_FACTORY, useValue: create },
      ],
    });
    realtime = TestBed.inject(RealtimeService);
  });
  afterEach(() => {
    realtime.stop();
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });
  function ready() {
    realtime.start();
    sockets.at(-1)!.message({ event: 'conexion.lista' });
  }

  it('abre una sola conexión y envía el JWT por subprotocolo, sin URL', () => {
    realtime.start();
    realtime.start();
    expect(create).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledWith('ws://127.0.0.1:8000/ws/notificaciones/', [
      'datapulse',
      'bearer.access-A',
    ]);
    expect(realtime.status()).toBe('connecting');
    sockets[0].message({ event: 'conexion.lista' });
    expect(realtime.status()).toBe('connected');
  });
  it.each([
    ['/api', 'https://app.example/pantalla', 'wss://app.example/ws/notificaciones/'],
    [
      'https://api.example/prefix/api',
      'https://app.example/',
      'wss://api.example/prefix/ws/notificaciones/',
    ],
    ['/prefix/api/', 'http://app.example/', 'ws://app.example/prefix/ws/notificaciones/'],
  ])('deriva el endpoint seguro desde %s', (api, document, expected) => {
    expect(socketUrl(api, document)).toBe(expected);
  });
  it('ignora JSON inválido, eventos desconocidos e ids no válidos; deduplica alertas', () => {
    const events: RealtimeEvent[] = [];
    realtime.events$.subscribe((event) => events.push(event));
    ready();
    sockets[0].onmessage?.(new MessageEvent('message', { data: 'not-json' }));
    for (const value of [
      null,
      {},
      { event: 'otra' },
      { event: 'alerta.creada', id: '2' },
      { event: 'alerta.creada', id: -1 },
    ])
      sockets[0].message(value);
    sockets[0].message({ event: 'alerta.creada', id: 2 });
    sockets[0].message({ event: 'alerta.creada', id: 2 });
    sockets[0].message({ event: 'ping' });
    expect(events).toEqual([{ event: 'conexion.lista' }, { event: 'alerta.creada', id: 2 }]);
  });
  it('agrupa sin perder alertas cuando también llegan cambios de dashboard', async () => {
    const updates: RealtimeUpdate[] = [];
    realtime.updates$.subscribe((update) => updates.push(update));
    ready();
    await vi.advanceTimersByTimeAsync(250);
    expect(updates).toEqual([{ alerts: true, dashboard: true, newAlerts: false }]);
    for (let id = 1; id <= 100; id++) {
      sockets[0].message({ event: 'alerta.creada', id });
      sockets[0].message({ event: 'dashboard.actualizado' });
    }
    await vi.advanceTimersByTimeAsync(4999);
    expect(updates).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(updates[1]).toEqual({ alerts: true, dashboard: true, newAlerts: true });
  });
  it('reconecta con espera creciente y descarta mensajes de conexiones anteriores', async () => {
    ready();
    const stale = sockets[0].onmessage!;
    sockets[0].end();
    expect(auth.logout).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1000);
    expect(sockets).toHaveLength(2);
    stale(new MessageEvent('message', { data: '{"event":"conexion.lista"}' }));
    expect(realtime.status()).toBe('reconnecting');
    sockets[1].end();
    await vi.advanceTimersByTimeAsync(1999);
    expect(sockets).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(sockets).toHaveLength(3);
  });
  it('vuelve a sincronizar al reconectar aunque haya perdido avisos', async () => {
    const updates: RealtimeUpdate[] = [];
    realtime.updates$.subscribe((value) => updates.push(value));
    ready();
    await vi.advanceTimersByTimeAsync(250);
    sockets[0].end();
    await vi.advanceTimersByTimeAsync(1000);
    sockets[1].message({ event: 'conexion.lista' });
    await vi.advanceTimersByTimeAsync(5000);
    expect(updates).toHaveLength(2);
    expect(updates[1]).toEqual({ alerts: true, dashboard: true, newAlerts: false });
  });
  it('los pings mantienen la conexión; una conexión silenciosa se recupera', async () => {
    ready();
    await vi.advanceTimersByTimeAsync(40000);
    sockets[0].message({ event: 'ping' });
    await vi.advanceTimersByTimeAsync(40000);
    expect(sockets).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(6000);
    expect(sockets).toHaveLength(2);
  });
  it('una renovación HTTP cambia el socket inmediatamente y cancela el anterior', () => {
    ready();
    auth.access = 'access-B';
    changed.next('access-B');
    expect(sockets[0].close).toHaveBeenCalled();
    expect(create).toHaveBeenLastCalledWith(expect.any(String), ['datapulse', 'bearer.access-B']);
    expect(sockets).toHaveLength(2);
  });
  it('un 4401 renueva y valida el perfil antes de abrir otro socket', () => {
    ready();
    sockets[0].end(4401);
    const profile = new Subject<typeof user>();
    auth.loadProfile.mockReturnValue(profile);
    expect(auth.renew).toHaveBeenCalledTimes(1);
    renewal.next('access-B');
    expect(sockets).toHaveLength(1);
    profile.next(user);
    expect(sockets).toHaveLength(2);
  });
  it('renueva antes de expirar un JWT real sin esperar otra petición HTTP', async () => {
    auth.access =
      'header.' + btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 40 })) + '.signature';
    ready();
    await vi.advanceTimersByTimeAsync(10000);
    expect(auth.renew).toHaveBeenCalledTimes(1);
  });
  it('un fallo de red al renovar conserva la sesión; un rechazo la cierra', () => {
    ready();
    sockets[0].end(4401);
    renewal.error(new HttpErrorResponse({ status: 503 }));
    expect(auth.logout).not.toHaveBeenCalled();
    expect(realtime.status()).toBe('reconnecting');
  });
  it('un refresh rechazado cierra sesión una sola vez', () => {
    ready();
    sockets[0].end(4401);
    renewal.error(new HttpErrorResponse({ status: 401 }));
    expect(auth.logout).toHaveBeenCalledTimes(1);
    expect(notify.show).toHaveBeenCalledTimes(1);
    expect(realtime.status()).toBe('stopped');
  });
  it('logout cancela renovación, recargas y reconexión aunque lleguen mensajes tardíos', async () => {
    const updates = vi.fn();
    realtime.updates$.subscribe(updates);
    ready();
    sockets[0].message({ event: 'alerta.creada', id: 3 });
    const stale = sockets[0].onmessage!;
    sockets[0].end(4401);
    auth.logout();
    renewal.next('late-token');
    stale(new MessageEvent('message', { data: '{"event":"alerta.creada","id":4}' }));
    await vi.advanceTimersByTimeAsync(120000);
    expect(auth.access).toBeNull();
    expect(sockets).toHaveLength(1);
    expect(updates).not.toHaveBeenCalled();
  });
  it('offline suspende reintentos y online abre una conexión nueva', async () => {
    ready();
    window.dispatchEvent(new Event('offline'));
    expect(realtime.status()).toBe('offline');
    await vi.advanceTimersByTimeAsync(120000);
    expect(sockets).toHaveLength(1);
    window.dispatchEvent(new Event('online'));
    expect(sockets).toHaveLength(2);
  });
  it('un logout en otra pestaña también cierra el socket', () => {
    ready();
    auth.access = null;
    window.dispatchEvent(new StorageEvent('storage', { key: 'datapulse.access', newValue: null }));
    expect(auth.logout).toHaveBeenCalledTimes(1);
    expect(sockets[0].close).toHaveBeenCalled();
  });
});
