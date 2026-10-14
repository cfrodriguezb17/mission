import { Component, inject, signal, computed, DestroyRef } from '@angular/core';
import { CurrencyPipe, DecimalPipe, DatePipe } from '@angular/common';
import { RouterLink, ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialog } from '@angular/material/dialog';
import { HttpErrorResponse } from '@angular/common/http';
import { forkJoin, finalize, switchMap, tap, catchError, EMPTY } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { PortafolioService } from '../../../core/services/portafolio.service';
import { PaisService } from '../../../core/services/pais.service';
import { NotifyService } from '../../../core/services/notify.service';
import { PortfolioDetail, Country, Position, label } from '../../../core/models/api.models';
import { PageState } from '../../../shared/page-state/page-state.component';
import { ChartSeries } from '../../../shared/charts/chart.component';
import { ConfirmDialog } from '../../../shared/confirm-dialog/confirm-dialog.component';
import { PortfolioEditDialog } from '../crear/editar-portafolio-dialog.component';
import { PositionDialog } from '../posicion-form/posicion-form.component';
import { ClosePositionDialog } from '../posicion-form/cerrar-posicion-dialog.component';
import { flag } from '../../../shared/utils/flags';
import { DistribucionChartComponent } from '../distribucion-chart/distribucion-chart.component';
@Component({
  imports: [
    RouterLink,
    CurrencyPipe,
    DecimalPipe,
    DatePipe,
    MatButtonModule,
    MatIconModule,
    PageState,
    DistribucionChartComponent,
  ],
  templateUrl: './detalle.component.html',
})
export class PortfolioDetailPage {
  private readonly api = inject(PortafolioService);
  private readonly countryApi = inject(PaisService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly notify = inject(NotifyService);
  private readonly destroy = inject(DestroyRef);
  readonly portfolio = signal<PortfolioDetail | null>(null);
  readonly countries = signal<Country[]>([]);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly busy = signal(false);
  readonly label = label;
  readonly flag = flag;
  readonly countryLabels = computed(
    () =>
      this.portfolio()?.resumen.distribucion_por_pais.map(
        (x) => this.countries().find((c) => c.codigo_iso === x.codigo)?.nombre ?? x.codigo,
      ) ?? [],
  );
  readonly countrySeries = computed<ChartSeries[]>(() => [
    {
      label: 'Capital USD',
      values: this.portfolio()?.resumen.distribucion_por_pais.map((x) => Number(x.monto_usd)) ?? [],
    },
  ]);
  readonly assetLabels = computed(
    () => this.portfolio()?.resumen.distribucion_por_tipo_activo.map((x) => label(x.codigo)) ?? [],
  );
  readonly assetSeries = computed<ChartSeries[]>(() => [
    {
      label: 'Capital USD',
      values:
        this.portfolio()?.resumen.distribucion_por_tipo_activo.map((x) => Number(x.monto_usd)) ??
        [],
    },
  ]);
  constructor() {
    this.route.paramMap
      .pipe(
        switchMap((params) => this.fetch(Number(params.get('id')))),
        takeUntilDestroyed(),
      )
      .subscribe();
  }
  private fetch(id: number) {
    this.loading.set(true);
    this.error.set(false);
    return forkJoin({ portfolio: this.api.detail(id), countries: this.countryApi.all() }).pipe(
      tap((data) => {
        this.portfolio.set(data.portfolio);
        this.countries.set(data.countries);
      }),
      catchError(() => {
        this.error.set(true);
        return EMPTY;
      }),
      finalize(() => this.loading.set(false)),
    );
  }
  load() {
    this.fetch(Number(this.route.snapshot.paramMap.get('id')))
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe();
  }
  private refresh() {
    const p = this.portfolio();
    if (!p) return;
    forkJoin({ detail: this.api.detail(p.id), summary: this.api.summary(p.id) })
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({
        next: (d) => this.portfolio.set({ ...d.detail, resumen: d.summary }),
        error: () => this.error.set(true),
      });
  }
  edit() {
    const p = this.portfolio();
    if (!p?.puede_editar) return;
    this.dialog
      .open(PortfolioEditDialog, { data: p, width: '600px', disableClose: true })
      .afterClosed()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe(() => this.refresh());
  }
  position(position?: Position) {
    const p = this.portfolio();
    if (!p?.puede_editar || this.busy()) return;
    this.dialog
      .open(PositionDialog, {
        data: { portfolio: p, position, countries: this.countries() },
        width: '700px',
        disableClose: true,
      })
      .afterClosed()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe(() => this.refresh());
  }
  close(position: Position) {
    const p = this.portfolio();
    if (!p?.puede_editar || this.busy()) return;
    this.dialog
      .open(ClosePositionDialog, { data: position, width: '470px' })
      .afterClosed()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe((date: string | null) => {
        if (!date) return;
        this.busy.set(true);
        this.api
          .closePosition(p.id, position.id, p.version, date)
          .pipe(
            finalize(() => this.busy.set(false)),
            takeUntilDestroyed(this.destroy),
          )
          .subscribe({
            next: () => {
              this.notify.show('Posición cerrada.');
              this.refresh();
            },
            error: (e) => {
              if (e instanceof HttpErrorResponse && e.status === 409) this.refresh();
            },
          });
      });
  }
  remove() {
    const p = this.portfolio();
    if (!p?.puede_eliminar || this.busy()) return;
    this.dialog
      .open(ConfirmDialog, {
        data: {
          title: 'Eliminar portafolio',
          message: `¿Quieres eliminar «${p.nombre}»? Dejará de aparecer en los listados.`,
          action: 'Eliminar',
        },
        width: '460px',
      })
      .afterClosed()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe((confirmed) => {
        if (!confirmed) return;
        this.busy.set(true);
        this.api
          .remove(p.id, p.version)
          .pipe(
            finalize(() => this.busy.set(false)),
            takeUntilDestroyed(this.destroy),
          )
          .subscribe({
            next: () => {
              this.notify.show('Portafolio eliminado.');
              void this.router.navigate(['/portafolios']);
            },
            error: (e) => {
              if (e instanceof HttpErrorResponse && e.status === 409) this.refresh();
            },
          });
      });
  }
  download() {
    const p = this.portfolio();
    if (!p || this.busy()) return;
    this.busy.set(true);
    this.api
      .pdf(p.id)
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroy),
      )
      .subscribe({
        next: (response) => {
          if (!response.body) return;
          const header = response.headers.get('Content-Disposition') ?? '';
          const filename = /filename="?([^";]+)"?/.exec(header)?.[1] ?? `portafolio-${p.id}.pdf`;
          const url = URL.createObjectURL(response.body);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename.replace(/[\/\\]/g, '_');
          a.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        },
        error: () => {},
      });
  }
}
