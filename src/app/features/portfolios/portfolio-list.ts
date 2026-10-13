import { Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { Subject, startWith, switchMap, catchError, EMPTY, finalize, debounceTime } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from '../../core/auth/auth.service';
import { PortfolioService } from '../../core/services/portfolio.service';
import { Portfolio, Page } from '../../core/models/api.models';
import { PageState } from '../../shared/page-state';
@Component({
  imports: [
    DatePipe,
    RouterLink,
    ReactiveFormsModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatPaginatorModule,
    PageState,
  ],
  template: `<div class="page-heading">
      <div>
        <span class="eyebrow">GESTIÓN DE INVERSIONES</span>
        <h1>Portafolios</h1>
        <p>Organiza tus inversiones y entiende tu exposición en la región.</p>
      </div>
      @if (auth.canWrite()) {
        <a mat-flat-button routerLink="/portafolios/nuevo"
          ><mat-icon>add</mat-icon>Nuevo portafolio</a
        >
      }
    </div>
    <form class="filter-bar" [formGroup]="filters">
      <mat-form-field class="search-field" appearance="outline"
        ><mat-label>Buscar portafolio</mat-label><mat-icon matPrefix>search</mat-icon
        ><input matInput formControlName="search" /></mat-form-field
      ><mat-form-field appearance="outline"
        ><mat-label>Mostrar</mat-label
        ><mat-select formControlName="scope"
          ><mat-option value="">Todos los visibles</mat-option
          ><mat-option value="own">Mis portafolios</mat-option
          ><mat-option value="public">Públicos</mat-option></mat-select
        ></mat-form-field
      >
    </form>
    <app-page-state
      [loading]="loading()"
      [error]="error()"
      [empty]="!loading() && !error() && !data()?.count"
      emptyTitle="No hay portafolios para mostrar"
      emptyMessage="Cambia los filtros o crea tu primer portafolio si tienes permisos de edición."
      (retry)="reload.next()"
    />
    @if (!loading() && !error()) {
      <div class="list-grid">
        @for (p of data()?.results; track p.id) {
          <article class="panel portfolio-card">
            <div class="card-top">
              <span class="kpi-icon"><mat-icon>work_outline</mat-icon></span>
              <div>
                <span class="pill" [class.own]="p.es_propio">{{
                  p.es_propio ? 'Propio' : 'Compartido'
                }}</span>
                <span class="pill">{{ p.es_publico ? 'Público' : 'Privado' }}</span>
              </div>
            </div>
            <h2>{{ p.nombre }}</h2>
            <p class="portfolio-description">{{ p.descripcion || 'Sin descripción.' }}</p>
            <div class="card-stats">
              <div>
                <small>Última actualización</small
                ><strong>{{ p.fecha_modificacion | date: 'd MMM yyyy' }}</strong>
              </div>
              <div>
                <small>Acceso</small><strong>{{ p.puede_editar ? 'Edición' : 'Consulta' }}</strong>
              </div>
            </div>
            <div class="card-bottom">
              <span class="small muted">Versión {{ p.version }}</span
              ><a [routerLink]="['/portafolios', p.id]"
                >Ver portafolio<mat-icon>arrow_forward</mat-icon></a
              >
            </div>
          </article>
        }
      </div>
      <mat-paginator
        [length]="data()?.count ?? 0"
        [pageIndex]="page"
        [pageSize]="12"
        hidePageSize
        aria-label="Paginación de portafolios"
        (page)="paginate($event)"
      />
    }`,
})
export class PortfolioList {
  readonly auth = inject(AuthService);
  private readonly api = inject(PortfolioService);
  readonly data = signal<Page<Portfolio> | null>(null);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly filters = inject(FormBuilder).nonNullable.group({ search: [''], scope: [''] });
  readonly reload = new Subject<void>();
  page = 0;
  constructor() {
    this.reload
      .pipe(
        startWith(undefined),
        switchMap(() => {
          this.loading.set(true);
          this.error.set(false);
          const f = this.filters.getRawValue();
          return this.api
            .list({
              search: f.search,
              propios: f.scope === 'own' ? true : undefined,
              es_publico: f.scope === 'public' ? true : undefined,
              ordering: '-fecha_modificacion',
              page: this.page + 1,
              page_size: 12,
            })
            .pipe(
              catchError(() => {
                this.error.set(true);
                return EMPTY;
              }),
              finalize(() => this.loading.set(false)),
            );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((v) => this.data.set(v));
    this.filters.valueChanges.pipe(debounceTime(300), takeUntilDestroyed()).subscribe(() => {
      this.page = 0;
      this.reload.next();
    });
  }
  paginate(event: PageEvent) {
    this.page = event.pageIndex;
    this.reload.next();
  }
}
