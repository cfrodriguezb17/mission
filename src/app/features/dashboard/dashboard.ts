import { Component, inject, signal, computed, DestroyRef } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { forkJoin, finalize, Subject, switchMap, catchError, EMPTY, startWith } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/services/api.service';
import { CountryService } from '../../core/services/country.service';
import { RiskService } from '../../core/services/risk.service';
import { AuthService } from '../../core/auth/auth.service';
import { NotifyService } from '../../core/services/notify.service';
import {
  Country,
  Risk,
  DashboardSummary,
  MapCountry,
  Trends,
  INDICATORS,
  label,
} from '../../core/models/api.models';
import { DataChart, ChartSeries } from '../../shared/chart';
import { RiskBadge } from '../../shared/risk-badge';
import { PageState } from '../../shared/page-state';
import { RiskMap } from './risk-map';
import { hasOperationIssues } from '../../shared/operation-result';
import { flag } from '../../shared/flags';
@Component({
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    ReactiveFormsModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatSelectModule,
    DataChart,
    RiskBadge,
    PageState,
    RiskMap,
  ],
  templateUrl: './dashboard.html',
})
export class Dashboard {
  private readonly api = inject(ApiService);
  private readonly countryApi = inject(CountryService);
  private readonly riskApi = inject(RiskService);
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
  readonly flag = flag;
  readonly number = Number;
  readonly label = label;
  readonly indicators = INDICATORS;
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
