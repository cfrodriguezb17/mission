import { Service, inject } from '@angular/core';
import {
  BehaviorSubject,
  Subject,
  Subscription,
  timer,
  switchMap,
  catchError,
  EMPTY,
  tap,
  merge,
  of,
  filter,
  map,
  startWith,
} from 'rxjs';
import { ApiService } from './api.service';
import { RealtimeService } from './realtime.service';
import { NotifyService } from './notify.service';
import { Alert, AlertSummary, Page, Params } from '../models/api.models';
@Service()
export class AlertaService {
  private readonly api = inject(ApiService);
  readonly realtime = inject(RealtimeService);
  private readonly notify = inject(NotifyService);
  private readonly state = new BehaviorSubject<AlertSummary | null>(null);
  readonly summary$ = this.state.asObservable();
  private readonly updates = new Subject<void>();
  readonly updates$ = this.updates.asObservable();
  private running?: Subscription;
  start() {
    this.stop();
    this.running = new Subscription();
    const notices = this.realtime.updates$.pipe(
      filter((update) => update.alerts),
      tap((update) => {
        if (update.newAlerts)
          this.notify.show('Hay nuevas alertas. Consúltalas en el centro de alertas.');
        this.updates.next();
      }),
      map(() => undefined),
    );
    const fallback = this.realtime.statusChanges$.pipe(
      startWith(this.realtime.status()),
      switchMap((status) =>
        status === 'connected' || status === 'offline' ? EMPTY : timer(30000, 30000),
      ),
      tap(() => this.updates.next()),
    );
    this.running.add(
      merge(of(undefined), notices, fallback)
        .pipe(switchMap(() => this.refresh().pipe(catchError(() => EMPTY))))
        .subscribe(),
    );
    this.running.add(this.realtime.ended$.subscribe(() => this.stop()));
  }
  stop() {
    this.running?.unsubscribe();
    this.running = undefined;
    this.state.next(null);
  }
  refresh() {
    return this.api
      .get<AlertSummary>('/alertas/resumen/', {}, true)
      .pipe(tap((value) => this.state.next(value)));
  }
  list(params: Params = {}, silent = false) {
    return this.api.get<Page<Alert>>('/alertas/', params, silent);
  }
  read(id: number) {
    return this.api.put<Alert>(`/alertas/${id}/leer/`, {});
  }
  readAll() {
    return this.api.put<{ marcadas: number }>('/alertas/leer-todas/', {});
  }
}
