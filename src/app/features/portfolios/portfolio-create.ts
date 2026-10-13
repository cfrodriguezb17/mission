import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { finalize } from 'rxjs';
import { PortfolioService } from '../../core/services/portfolio.service';
import { NotifyService } from '../../core/services/notify.service';
import { trimmedName, fieldError, applyServerErrors } from '../../shared/form-utils';
@Component({
  imports: [
    RouterLink,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatCheckboxModule,
    MatButtonModule,
    MatIconModule,
  ],
  template: `<a class="back-link" routerLink="/portafolios"
      ><mat-icon>arrow_back</mat-icon>Todos los portafolios</a
    >
    <div class="page-heading">
      <div>
        <span class="eyebrow">GESTIÓN DE INVERSIONES</span>
        <h1>Nuevo portafolio</h1>
        <p>Define tu estrategia y empieza a agregar posiciones.</p>
      </div>
    </div>
    <section class="panel form-panel">
      <div class="panel-heading"><h2>Información del portafolio</h2></div>
      <form [formGroup]="form" (ngSubmit)="save()">
        <mat-form-field appearance="outline"
          ><mat-label>Nombre</mat-label
          ><input matInput formControlName="nombre" maxlength="100" /><mat-hint>{{
            form.controls.nombre.pending
              ? 'Comprobando disponibilidad…'
              : 'Entre 3 y 100 caracteres.'
          }}</mat-hint
          ><mat-error>{{ fieldError(form.controls.nombre) }}</mat-error></mat-form-field
        >
        @if (form.controls.nombre.hasError('availability')) {
          <button type="button" mat-button (click)="form.controls.nombre.updateValueAndValidity()">
            Volver a comprobar nombre
          </button>
        }
        <mat-form-field appearance="outline"
          ><mat-label>Descripción</mat-label
          ><textarea matInput formControlName="descripcion" rows="4" maxlength="500"></textarea
          ><mat-hint align="end">{{ form.controls.descripcion.value.length }} / 500</mat-hint
          ><mat-error>{{ fieldError(form.controls.descripcion) }}</mat-error></mat-form-field
        ><mat-checkbox formControlName="es_publico">Portafolio público</mat-checkbox>
        <p class="small muted">
          Los portafolios públicos son visibles para el equipo y editables por analistas.
        </p>
        @if (error()) {
          <p class="form-error" role="alert">{{ error() }}</p>
        }
        <div class="form-actions">
          <a mat-button routerLink="/portafolios">Cancelar</a
          ><button mat-flat-button [disabled]="form.invalid || form.pending || saving()">
            {{ saving() ? 'Creando…' : 'Crear portafolio' }}
          </button>
        </div>
      </form>
    </section>`,
})
export class PortfolioCreate {
  private readonly api = inject(PortfolioService);
  private readonly router = inject(Router);
  private readonly notify = inject(NotifyService);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly fieldError = fieldError;
  readonly form = inject(FormBuilder).nonNullable.group({
    nombre: [
      '',
      {
        validators: [Validators.required, trimmedName],
        asyncValidators: [this.api.nameValidator()],
      },
    ],
    descripcion: ['', Validators.maxLength(500)],
    es_publico: [false],
  });
  save() {
    if (this.form.invalid || this.form.pending || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.error.set('');
    const value = this.form.getRawValue();
    this.api
      .create({ ...value, nombre: value.nombre.trim() })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (p) => {
          this.notify.show('Portafolio creado.');
          void this.router.navigate(['/portafolios', p.id]);
        },
        error: (e) => this.error.set(applyServerErrors(this.form, e)),
      });
  }
}
