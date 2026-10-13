import { Component, inject, signal, computed, DestroyRef } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DecimalPipe, DatePipe, NgOptimizedImage } from '@angular/common';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { forkJoin, finalize, switchMap, catchError, EMPTY, tap } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { PaisService } from '../../../core/services/pais.service';
import { RiesgoService } from '../../../core/services/riesgo.service';
import {
  Country,
  Indicator,
  Risk,
  Exchange,
  INDICATORS,
  label,
} from '../../../core/models/api.models';
import { DataChart, ChartSeries } from '../../../shared/charts/chart.component';
import { RiskBadge } from '../../../shared/risk-badge/risk-badge.component';
import { PageState } from '../../../shared/page-state/page-state.component';
import { localDate } from '../../../shared/utils/form-utils';
import { flag } from '../../../shared/utils/flags';
@Component({
  imports: [
    RouterLink,
    DecimalPipe,
    DatePipe,
    NgOptimizedImage,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatIconModule,
    DataChart,
    RiskBadge,
    PageState,
  ],
  templateUrl: './detalle-pais.component.html',
})
export class CountryDetail {
  private readonly api = inject(PaisService);
  private readonly riskApi = inject(RiesgoService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroy = inject(DestroyRef);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly country = signal<Country | null>(null);
  readonly indicators = signal<Indicator[]>([]);
  readonly history = signal<Risk[]>([]);
  readonly exchanges = signal<Exchange[]>([]);
  readonly current = signal<Risk | null>(null);
  readonly chosen = signal('PIB');
  readonly selector = new FormControl('PIB', { nonNullable: true });
  readonly catalog = INDICATORS;
  readonly label = label;
  readonly number = Number;
  readonly flag = flag;
  readonly evidence = (value: unknown) => JSON.stringify(value, null, 2);
  readonly latest = computed(() =>
    this.catalog.map((type) => ({
      type,
      ...{
        value: this.indicators()
          .filter((x) => x.tipo === type.code)
          .sort((a, b) => b.anio - a.anio)
          .at(0),
      },
    })),
  );
  readonly years = computed(() => {
    const end = new Date().getFullYear() - 1;
    return Array.from({ length: 5 }, (_, i) => end - 4 + i);
  });
  readonly indicatorLabels = computed(() => this.years().map(String));
  readonly indicatorSeries = computed<ChartSeries[]>(() => [
    {
      label: label(this.chosen()),
      values: this.years().map((year) => {
        const i = this.indicators().find((x) => x.tipo === this.chosen() && x.anio === year);
        return i ? Number(i.valor) : null;
      }),
    },
  ]);
  readonly exchangeLabels = computed(() => this.exchanges().map((x) => x.fecha));
  readonly exchangeSeries = computed<ChartSeries[]>(() => [
    {
      label: `USD por ${this.country()?.moneda_codigo ?? 'moneda local'}`,
      values: this.exchanges().map((x) => Number(x.tasa)),
      color: '#0d9488',
    },
  ]);
  readonly simulated = computed(
    () =>
      this.indicators().some((i) => i.es_simulado) ||
      this.exchanges().some((x) => x.es_simulado) ||
      this.current()?.detalle_calculo.contiene_simulaciones,
  );
  readonly scores = computed(() => {
    const r = this.current();
    return r
      ? [
          { label: 'Económico', weight: '40 %', value: r.score_economico },
          { label: 'Cambiario', weight: '30 %', value: r.score_cambiario },
          { label: 'Estabilidad', weight: '30 %', value: r.score_estabilidad },
        ]
      : [];
  });
  constructor() {
    this.selector.valueChanges.pipe(takeUntilDestroyed()).subscribe((v) => this.chosen.set(v));
    this.route.paramMap
      .pipe(
        switchMap((params) => this.fetch(params.get('codigo') ?? '')),
        takeUntilDestroyed(),
      )
      .subscribe();
  }
  private fetch(code: string) {
    this.loading.set(true);
    this.error.set(false);
    const start = new Date();
    start.setDate(start.getDate() - 29);
    return forkJoin({
      country: this.api.detail(code),
      indicators: this.api.indicators(code),
      exchanges: this.api.exchange(code, {
        fecha_inicio: localDate(start),
        fecha_fin: localDate(),
        ordering: 'fecha',
      }),
      risk: this.riskApi.detail(code),
      history: this.riskApi.history(code, { ordering: '-fecha_calculo' }),
    }).pipe(
      tap((data) => {
        this.country.set(data.country);
        this.indicators.set(data.indicators);
        this.exchanges.set(data.exchanges);
        this.current.set(data.risk.ultimo);
        this.history.set(data.history);
      }),
      catchError(() => {
        this.error.set(true);
        return EMPTY;
      }),
      finalize(() => this.loading.set(false)),
    );
  }
  load() {
    this.fetch(this.route.snapshot.paramMap.get('codigo') ?? '')
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe();
  }
}
