import { DestroyRef, InjectionToken, Service, inject, signal } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Subject, Subscription, finalize, switchMap } from 'rxjs';
import { AuthService } from '../auth/services/auth.service';
import { ApiService } from './api.service';
import { NotifyService } from './notify.service';

export type RealtimeEvent =
  | { event: 'conexion.lista' }
  | { event: 'dashboard.actualizado' }
  | { event: 'alerta.creada'; id: number };
export type RealtimeStatus = 'stopped' | 'connecting' | 'connected' | 'reconnecting' | 'offline';
export interface RealtimeUpdate {
  alerts: boolean;
  dashboard: boolean;
  newAlerts: boolean;
}
export const SOCKET_FACTORY = new InjectionToken<(url: string, protocols: string[]) => WebSocket>(
  'WebSocket factory',
  { providedIn: 'root', factory: () => (url, protocols) => new WebSocket(url, protocols) },
);

export function socketUrl(apiBase: string, documentBase: string): string {
  const api = new URL(apiBase.replace(/\/$/, '') + '/', documentBase);
  const url = new URL('../ws/notificaciones/', api);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

function expiresAt(access: string): number | null {
  try {
    const encoded = access.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload: unknown = JSON.parse(
      atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, '=')),
    );
    if (typeof payload !== 'object' || payload === null || !('exp' in payload)) return null;
    return typeof payload.exp === 'number' && Number.isFinite(payload.exp)
      ? payload.exp * 1000
      : null;
  } catch {
    return null;
  }
}

@Service()
export class RealtimeService {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly notify = inject(NotifyService);
  private readonly document = inject(DOCUMENT);
  private readonly createSocket = inject(SOCKET_FACTORY);
  private readonly state = signal<RealtimeStatus>('stopped');
  readonly status = this.state.asReadonly();
  private readonly events = new Subject<RealtimeEvent>();
  readonly events$ = this.events.asObservable();
  private readonly updates = new Subject<RealtimeUpdate>();
  readonly updates$ = this.updates.asObservable();
  private readonly statusChanges = new Subject<RealtimeStatus>();
  readonly statusChanges$ = this.statusChanges.asObservable();
  private readonly ended = new Subject<void>();
  readonly ended$ = this.ended.asObservable();
  private socket?: WebSocket;
  private socketToken?: string;
  private session?: Subscription;
  private renewal?: Subscription;
  private retryTimer?: ReturnType<typeof setTimeout>;
  private expiryTimer?: ReturnType<typeof setTimeout>;
  private heartbeatTimer?: ReturnType<typeof setTimeout>;
  private updateTimer?: ReturnType<typeof setTimeout>;
  private lastUpdate = 0;
  private pending: RealtimeUpdate = { alerts: false, dashboard: false, newAlerts: false };
  private readonly alertIds = new Set<number>();
  private active = false;
  private renewing = false;
  private online = true;
  private attempts = 0;
  private connectedAt = 0;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.stop());
  }

  start(): void {
    if (this.active) return;
    this.active = true;
    this.online = this.document.defaultView?.navigator.onLine !== false;
    this.session = this.auth.accessChanges$.subscribe((access) => {
      if (!access) this.stop();
      else if (!this.renewing) this.connectOrRenew(access);
    });
    this.document.defaultView?.addEventListener('online', this.onOnline);
    this.document.defaultView?.addEventListener('offline', this.onOffline);
    this.document.defaultView?.addEventListener('storage', this.onStorage);
    this.connectOrRenew(this.auth.access);
  }

  stop(): void {
    this.active = false;
    this.session?.unsubscribe();
    this.session = undefined;
    this.renewal?.unsubscribe();
    this.renewal = undefined;
    clearTimeout(this.retryTimer);
    clearTimeout(this.expiryTimer);
    clearTimeout(this.updateTimer);
    this.updateTimer = undefined;
    this.lastUpdate = 0;
    this.pending = { alerts: false, dashboard: false, newAlerts: false };
    this.detach();
    this.attempts = 0;
    this.alertIds.clear();
    this.document.defaultView?.removeEventListener('online', this.onOnline);
    this.document.defaultView?.removeEventListener('offline', this.onOffline);
    this.document.defaultView?.removeEventListener('storage', this.onStorage);
    this.setStatus('stopped');
    this.ended.next();
  }

  private readonly onOnline = () => {
    this.online = true;
    this.connectOrRenew(this.auth.access);
  };
  private readonly onOffline = () => {
    this.online = false;
    clearTimeout(this.retryTimer);
    clearTimeout(this.expiryTimer);
    clearTimeout(this.updateTimer);
    this.updateTimer = undefined;
    this.detach();
    this.setStatus('offline');
  };
  private readonly onStorage = (event: StorageEvent) => {
    if ((event.key === 'datapulse.access' || event.key === null) && !this.auth.access) {
      this.auth.logout();
    }
  };

  private connectOrRenew(access: string | null): void {
    if (!this.active || !this.auth.user()) return;
    if (!this.online) {
      this.setStatus('offline');
      return;
    }
    if (!access) {
      this.stop();
      return;
    }
    const expiry = expiresAt(access);
    if (expiry !== null && expiry <= Date.now()) this.renewAccess();
    else this.connect(access);
  }

  private connect(access: string): void {
    if (!this.active || !this.online || this.auth.access !== access) return;
    if (this.socket && this.socketToken === access) return;
    clearTimeout(this.retryTimer);
    clearTimeout(this.expiryTimer);
    this.detach();
    this.setStatus(this.attempts ? 'reconnecting' : 'connecting');
    let socket: WebSocket;
    try {
      socket = this.createSocket(socketUrl(this.api.base, this.document.baseURI), [
        'datapulse',
        `bearer.${access}`,
      ]);
    } catch {
      this.retry();
      return;
    }
    this.socket = socket;
    this.socketToken = access;
    this.armHeartbeat(10000);
    const current = () => this.active && this.socket === socket && this.auth.access === access;
    socket.onmessage = (message: MessageEvent<unknown>) => {
      if (!current() || typeof message.data !== 'string' || message.data.length > 4096) return;
      let value: unknown;
      try {
        value = JSON.parse(message.data);
      } catch {
        return;
      }
      if (typeof value !== 'object' || value === null || !('event' in value)) return;
      if (value.event === 'ping' || value.event === 'pong') {
        this.armHeartbeat();
        return;
      }
      if (value.event === 'conexion.lista') {
        this.armHeartbeat();
        this.connectedAt = Date.now();
        this.setStatus('connected');
        this.publish({ event: 'conexion.lista' });
      } else if (this.status() === 'connected' && value.event === 'dashboard.actualizado') {
        this.armHeartbeat();
        this.publish({ event: 'dashboard.actualizado' });
      } else if (
        this.status() === 'connected' &&
        value.event === 'alerta.creada' &&
        'id' in value &&
        typeof value.id === 'number' &&
        Number.isSafeInteger(value.id) &&
        value.id > 0
      ) {
        this.armHeartbeat();
        if (this.alertIds.has(value.id)) return;
        this.alertIds.add(value.id);
        if (this.alertIds.size > 256) this.alertIds.delete(this.alertIds.values().next().value!);
        this.publish({ event: 'alerta.creada', id: value.id });
      }
    };
    // El navegador no expone el HTTP del handshake. Un error genérico no revoca la sesión.
    socket.onerror = () => {};
    socket.onclose = (event) => {
      if (!current()) return;
      if (this.connectedAt && Date.now() - this.connectedAt >= 30000) this.attempts = 0;
      this.detach();
      if (event.code === 4401) this.renewAccess();
      else this.retry(event.code === 4429 ? 60000 : undefined);
    };
    this.scheduleRenewal(access);
  }

  private scheduleRenewal(access: string): void {
    const expiry = expiresAt(access);
    if (expiry === null) return;
    const lead = this.auth.refreshToken ? 30000 : 0;
    this.expiryTimer = setTimeout(
      () => this.renewAccess(),
      Math.max(1000, Math.min(2147483647, expiry - Date.now() - lead)),
    );
  }

  private renewAccess(): void {
    if (!this.active || this.renewing || !this.online) return;
    if (!this.socket) this.setStatus('reconnecting');
    if (!this.auth.refreshToken) {
      this.expireSession();
      return;
    }
    this.renewing = true;
    this.renewal = this.auth
      .renew()
      .pipe(
        switchMap(() => this.auth.loadProfile()),
        finalize(() => {
          this.renewing = false;
        }),
      )
      .subscribe({
        next: () => {
          if (this.active && this.auth.access) this.connect(this.auth.access);
        },
        error: (error: unknown) => {
          if (!this.active) return;
          if (
            error instanceof HttpErrorResponse &&
            (error.status === 401 || error.status === 403)
          ) {
            this.expireSession();
          } else {
            this.detach();
            this.retry();
          }
        },
      });
  }

  private expireSession(): void {
    if (this.auth.access) this.notify.show('Tu sesión expiró. Inicia sesión nuevamente.');
    this.auth.logout();
  }

  private retry(delay?: number): void {
    if (!this.active || !this.online) return;
    this.setStatus('reconnecting');
    clearTimeout(this.retryTimer);
    clearTimeout(this.expiryTimer);
    const wait =
      delay ??
      Math.min(30000, 1000 * 2 ** Math.min(this.attempts++, 5)) + Math.floor(Math.random() * 250);
    this.retryTimer = setTimeout(() => this.connectOrRenew(this.auth.access), wait);
  }

  private armHeartbeat(delay = 45000): void {
    clearTimeout(this.heartbeatTimer);
    this.heartbeatTimer = setTimeout(() => {
      this.detach();
      this.retry();
    }, delay);
  }

  private detach(): void {
    clearTimeout(this.heartbeatTimer);
    this.connectedAt = 0;
    const socket = this.socket;
    this.socket = undefined;
    this.socketToken = undefined;
    if (socket) {
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      socket.close(1000, 'Fin de conexión');
    }
  }

  private setStatus(status: RealtimeStatus): void {
    if (this.status() === status) return;
    this.state.set(status);
    this.statusChanges.next(status);
  }

  private publish(event: RealtimeEvent): void {
    this.events.next(event);
    if (event.event !== 'dashboard.actualizado') this.pending.alerts = true;
    this.pending.dashboard = true;
    if (event.event === 'alerta.creada') this.pending.newAlerts = true;
    if (this.updateTimer !== undefined) return;
    // Un solo lote compartido limita las recargas de todos los consumidores.
    const delay = Math.max(250, this.lastUpdate + 5000 - Date.now());
    this.updateTimer = setTimeout(() => {
      this.updateTimer = undefined;
      if (!this.active) return;
      const update = this.pending;
      this.pending = { alerts: false, dashboard: false, newAlerts: false };
      this.lastUpdate = Date.now();
      this.updates.next(update);
    }, delay);
  }
}
