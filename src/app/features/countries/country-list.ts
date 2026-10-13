import { Component, inject, signal, DestroyRef } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatIconModule } from '@angular/material/icon';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { Subject, startWith, switchMap, catchError, EMPTY, finalize, debounceTime } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CountryService } from '../../core/services/country.service';
import { Country, Page, REGIONS, label } from '../../core/models/api.models';
import { PageState } from '../../shared/page-state';
import { flag } from '../../shared/flags';
@Component({
  imports: [
    DecimalPipe,
    RouterLink,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatIconModule,
    MatPaginatorModule,
    PageState,
  ],
  template: `<div class="page-heading">
      <div>
        <span class="eyebrow">EXPLORA LA REGIÓN</span>
        <h1>Países y mercados</h1>
        <p>Conoce los indicadores y el perfil de riesgo de cada economía.</p>
      </div>
    </div>
    <form class="filter-bar" [formGroup]="filters">
      <mat-form-field appearance="outline" class="search-field"
        ><mat-label>Buscar país</mat-label><mat-icon matPrefix>search</mat-icon
        ><input
          matInput
          formControlName="search"
          placeholder="Nombre o código del país" /></mat-form-field
      ><mat-form-field appearance="outline"
        ><mat-label>Región</mat-label
        ><mat-select formControlName="region"
          ><mat-option value="">Todas las regiones</mat-option>
          @for (region of regions; track region.code) {
            <mat-option [value]="region.code">{{ region.label }}</mat-option>
          }
        </mat-select></mat-form-field
      ><mat-form-field appearance="outline"
        ><mat-label>Orden</mat-label
        ><mat-select formControlName="ordering"
          ><mat-option value="nombre">Nombre A–Z</mat-option
          ><mat-option value="-nombre">Nombre Z–A</mat-option></mat-select
        ></mat-form-field
      >
    </form>
    <app-page-state
      [loading]="loading()"
      [error]="error()"
      [empty]="!loading() && !error() && !data()?.count"
      emptyTitle="No encontramos países"
      emptyMessage="Prueba con otro nombre o región."
      (retry)="reload.next()"
    />
    @if (!loading() && !error()) {
      <div class="list-grid">
        @for (country of data()?.results; track country.codigo_iso) {
          <article class="panel country-card">
            <div class="card-top">
              <span class="flag-large" aria-hidden="true">{{ flag(country.codigo_iso) }}</span
              ><span class="pill">{{ label(country.region) }}</span>
            </div>
            <h2>{{ country.nombre }}</h2>
            <p>{{ country.codigo_iso }} · {{ country.moneda_nombre }}</p>
            <div class="card-stats">
              <div>
                <small>Moneda</small><strong>{{ country.moneda_codigo }}</strong>
              </div>
              <div>
                <small>Población</small
                ><strong>{{
                  country.poblacion === null ? 'Sin datos' : (country.poblacion | number)
                }}</strong>
              </div>
            </div>
            <div class="card-bottom">
              <span class="small muted">Indicadores y riesgo</span
              ><a [routerLink]="['/paises', country.codigo_iso]"
                >Explorar<mat-icon>arrow_forward</mat-icon></a
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
        aria-label="Paginación de países"
        (page)="paginate($event)"
      />
    }`,
})
export class CountryList {
  private readonly api = inject(CountryService);
  readonly data = signal<Page<Country> | null>(null);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly regions = REGIONS;
  readonly flag = flag;
  readonly label = label;
  readonly filters = inject(FormBuilder).nonNullable.group({
    search: [''],
    region: [''],
    ordering: ['nombre'],
  });
  readonly reload = new Subject<void>();
  page = 0;
  constructor() {
    this.reload
      .pipe(
        startWith(undefined),
        switchMap(() => {
          this.loading.set(true);
          this.error.set(false);
          return this.api
            .list({ ...this.filters.getRawValue(), page: this.page + 1, page_size: 12 })
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
      .subscribe((data) => this.data.set(data));
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
