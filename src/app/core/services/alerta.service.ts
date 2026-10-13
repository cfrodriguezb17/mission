import { Service, inject } from '@angular/core';
import { BehaviorSubject, Subscription, timer, switchMap, catchError, EMPTY, tap } from 'rxjs';
import { ApiService } from './api.service';
import { Alert, AlertSummary, Page, Params } from '../models/api.models';
@Service()
export class AlertaService {
  private readonly api = inject(ApiService);
  private readonly state = new BehaviorSubject<AlertSummary | null>(null);
  readonly summary$ = this.state.asObservable();
  private polling?: Subscription;
  start() {
    this.stop();
    this.polling = timer(0, 30000)
      .pipe(switchMap(() => this.refresh().pipe(catchError(() => EMPTY))))
      .subscribe();
  }
  stop() {
    this.polling?.unsubscribe();
    this.polling = undefined;
    this.state.next(null);
  }
  refresh() {
    return this.api
      .get<AlertSummary>('/alertas/resumen/', {}, true)
      .pipe(tap((value) => this.state.next(value)));
  }
  list(params: Params = {}) {
    return this.api.get<Page<Alert>>('/alertas/', params);
  }
  read(id: number) {
    return this.api.put<Alert>(`/alertas/${id}/leer/`, {});
  }
  readAll() {
    return this.api.put<{ marcadas: number }>('/alertas/leer-todas/', {});
  }
}
