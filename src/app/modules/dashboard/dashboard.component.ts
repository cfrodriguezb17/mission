import { Component, inject, signal, computed, DestroyRef } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormBuilder, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { forkJoin, finalize, Subject, switchMap, catchError, EMPTY, startWith } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/services/api.service';
import { PaisService } from '../../core/services/pais.service';
import { RiesgoService } from '../../core/services/riesgo.service';
import { AuthService } from '../../core/auth/services/auth.service';
import { NotifyService } from '../../core/services/notify.service';
import { Country, Risk, DashboardSummary, MapCountry, Trends } from '../../core/models/api.models';
import { ChartSeries } from '../../shared/charts/chart.component';
import { PageState } from '../../shared/page-state/page-state.component';
import { RiskMap } from './mapa-riesgo/mapa-riesgo.component';
import { hasOperationIssues } from '../../shared/utils/operation-result';
import { RoleDirective } from '../../shared/directives/role.directive';
import { KpiCardsComponent } from './kpi-cards/kpi-cards.component';
import { TablaRankingComponent } from './tabla-ranking/tabla-ranking.component';
import { GraficoTendenciasComponent } from './grafico-tendencias/grafico-tendencias.component';
@Component({
  imports: [
    DatePipe,
    MatButtonModule,
    MatIconModule,
    PageState,
    RiskMap,
    RoleDirective,
    KpiCardsComponent,
    TablaRankingComponent,
    GraficoTendenciasComponent,
  ],
  templateUrl: './dashboard.component.html',
})
export class Dashboard {
  private readonly api = inject(ApiService);
  private readonly countryApi = inject(PaisService);
  private readonly riskApi = inject(RiesgoService);
  readonly auth = inject(AuthService);
  private readonly notify = inject(NotifyService);
  private readonly destroy = inject(DestroyRef);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly summary = signal<DashboardSummary | null>(null);
  readonly countries = signal<Country[]>([]);
  readonly ranking = signal<Risk[]>([]);
  readonly map = signal<MapCountry[]>([]);
  readonly trends = signal<Trends | null>(null);
  readonly trendLoading = signal(false);
  readonly trendError = signal(false);
  readonly busy = signal(false);
  readonly jobMessage = signal('');
  readonly today = new Date();
  readonly filters = inject(FormBuilder).nonNullable.group({
    tipo: ['PIB', Validators.required],
    paises: [
      ['CO', 'BR', 'MX'],
      [Validators.required, Validators.maxLength(3)],
    ],
  });
  private readonly trendReload = new Subject<void>();
  readonly trendLabels = computed(
    () => this.trends()?.results[0]?.valores.map((v) => String(v.anio)) ?? [],
  );
  readonly trendSeries = computed<ChartSeries[]>(
    () =>
      this.trends()?.results.map((c) => ({
        label: c.nombre_pais,
        values: c.valores.map((v) => (v.valor === null ? null : Number(v.valor))),
      })) ?? [],
  );
  readonly trendNotice = computed(
    () =>
      this.trends()?.results.some(
        (c) => c.datos_parciales || c.valores.some((v) => v.es_simulado),
      ) ?? false,
  );
  constructor() {
    this.load();
    this.trendReload
      .pipe(
        startWith(undefined),
        switchMap(() => {
          if (this.filters.invalid) return EMPTY;
          this.trendLoading.set(true);
          this.trendError.set(false);
          const value = this.filters.getRawValue();
          return this.api
            .get<Trends>('/dashboard/tendencias/', {
              tipo: value.tipo,
              paises: value.paises.join(','),
              page_size: 100,
            })
            .pipe(
              catchError(() => {
                this.trendError.set(true);
                this.trends.set(null);
                return EMPTY;
              }),
              finalize(() => this.trendLoading.set(false)),
            );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((t) => this.trends.set(t));
    this.filters.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.trendReload.next());
  }
  load() {
    this.loading.set(true);
    this.error.set(false);
    forkJoin({
      summary: this.api.get<DashboardSummary>('/dashboard/resumen/'),
      countries: this.countryApi.all(),
      ranking: this.riskApi.ranking(),
      map: this.api.all<MapCountry>('/dashboard/mapa/'),
    })
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.loading.set(false)),
      )
      .subscribe({
        next: (data) => {
          this.summary.set(data.summary);
          this.countries.set(data.countries);
          this.ranking.set(data.ranking);
          this.map.set(data.map);
        },
        error: () => this.error.set(true),
      });
  }
  reloadTrends() {
    this.trendReload.next();
  }
  runJob(kind: 'sync' | 'risk') {
    if (this.busy() || this.auth.user()?.rol !== 'ADMIN') return;
    this.busy.set(true);
    this.jobMessage.set('');
    this.api
      .post<Record<string, unknown>>(
        kind === 'sync' ? '/paises/sync-indicadores/' : '/riesgo/calcular/',
        {},
      )
      .pipe(
        takeUntilDestroyed(this.destroy),
        finalize(() => this.busy.set(false)),
      )
      .subscribe({
        next: (result) => {
          const partial = result['estado'] === 'PARCIAL' || hasOperationIssues(result);
          const message = partial
            ? 'Proceso parcial: hay datos faltantes, errores o etapas pendientes. Se conservan los datos disponibles.'
            : 'Proceso completado. Los datos fueron actualizados.';
          this.jobMessage.set(message);
          this.notify.show(message);
          this.load();
          this.reloadTrends();
        },
        error: () =>
          this.jobMessage.set(
            'No se completó el proceso. Puedes seguir consultando los datos guardados.',
          ),
      });
  }
}
