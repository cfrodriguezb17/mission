import { Component, inject, signal, DestroyRef } from '@angular/core';
import { DatePipe, AsyncPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { Subject, startWith, switchMap, catchError, EMPTY, finalize, merge, map } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AlertaService } from '../../../core/services/alerta.service';
import { NotifyService } from '../../../core/services/notify.service';
import { Alert, Page, label } from '../../../core/models/api.models';
import { PageState } from '../../../shared/page-state/page-state.component';
@Component({
  imports: [
    DatePipe,
    AsyncPipe,
    RouterLink,
    ReactiveFormsModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatSelectModule,
    MatPaginatorModule,
    PageState,
  ],
  templateUrl: './panel-alertas.component.html',
})
export class AlertsPage {
  readonly api = inject(AlertaService);
  private readonly notify = inject(NotifyService);
  private readonly destroy = inject(DestroyRef);
  readonly data = signal<Page<Alert> | null>(null);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly busy = signal(false);
  readonly label = label;
  readonly filters = inject(FormBuilder).nonNullable.group({
    leida: [''],
    tipo_alerta: [''],
    severidad: [''],
  });
  readonly reload = new Subject<void>();
  private readonly backgroundReload = new Subject<void>();
  page = 0;
  constructor() {
    merge(this.reload.pipe(map(() => false)), this.backgroundReload.pipe(map(() => true)))
      .pipe(
        startWith(false),
        switchMap((background) => {
          if (!background || !this.data()) {
            this.loading.set(true);
            this.error.set(false);
          }
          return this.api
            .list(
              {
                ...this.filters.getRawValue(),
                ordering: '-fecha_creacion',
                page: this.page + 1,
                page_size: 20,
              },
              background,
            )
            .pipe(
              catchError(() => {
                if (!background || !this.data()) this.error.set(true);
                return EMPTY;
              }),
              finalize(() => this.loading.set(false)),
            );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((v) => {
        this.data.set(v);
        this.error.set(false);
      });
    this.api.updates$.pipe(takeUntilDestroyed()).subscribe(() => this.backgroundReload.next());
    this.filters.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => {
      this.page = 0;
      this.reload.next();
    });
  }
  paginate(event: PageEvent) {
    this.page = event.pageIndex;
    this.reload.next();
  }
  read(alert: Alert) {
    if (this.busy()) return;
    this.busy.set(true);
    this.api
      .read(alert.id)
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroy),
      )
      .subscribe({ next: () => this.updated(), error: () => {} });
  }
  readAll() {
    if (this.busy()) return;
    this.busy.set(true);
    this.api
      .readAll()
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroy),
      )
      .subscribe({
        next: (result) => {
          this.notify.show(`${result.marcadas} alertas marcadas como leídas.`);
          this.page = 0;
          this.updated();
        },
        error: () => {},
      });
  }
  private updated() {
    this.reload.next();
    this.api
      .refresh()
      .pipe(takeUntilDestroyed(this.destroy))
      .subscribe({ error: () => {} });
  }
}
