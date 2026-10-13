import { Component, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatButtonModule } from '@angular/material/button';
import { finalize } from 'rxjs';
import { PortfolioDetail } from '../../core/models/api.models';
import { PortfolioService } from '../../core/services/portfolio.service';
import { fieldError, trimmedName, applyServerErrors } from '../../shared/form-utils';
@Component({
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatCheckboxModule,
    MatButtonModule,
  ],
  template: `<h2 mat-dialog-title>Editar portafolio</h2>
    <mat-dialog-content
      ><form id="portfolio-edit" class="dialog-form" [formGroup]="form" (ngSubmit)="save()">
        <mat-form-field appearance="outline"
          ><mat-label>Nombre</mat-label
          ><input matInput formControlName="nombre" maxlength="100" /><mat-hint>{{
            form.controls.nombre.pending ? 'Comprobando disponibilidad…' : ''
          }}</mat-hint
          ><mat-error>{{ fieldError(form.controls.nombre) }}</mat-error></mat-form-field
        >
        @if (form.controls.nombre.hasError('availability')) {
          <button mat-button type="button" (click)="form.controls.nombre.updateValueAndValidity()">
            Volver a comprobar nombre
          </button>
        }
        <mat-form-field appearance="outline"
          ><mat-label>Descripción</mat-label
          ><textarea matInput formControlName="descripcion" rows="4" maxlength="500"></textarea
          ><mat-hint align="end">{{ form.controls.descripcion.value.length }} / 500</mat-hint
          ><mat-error>{{ fieldError(form.controls.descripcion) }}</mat-error></mat-form-field
        >
        @if (current().puede_cambiar_visibilidad) {
          <mat-checkbox formControlName="es_publico">Portafolio público</mat-checkbox>
        }
        @if (error()) {
          <p class="form-error" role="alert">{{ error() }}</p>
        }
        @if (conflict()) {
          <div class="notice">
            Información actual: {{ current().nombre }} · {{ current().descripcion }} ·
            {{ current().es_publico ? 'Público' : 'Privado' }}. Tu borrador se conserva. Revisa los
            cambios antes de confirmar.<button
              mat-button
              type="button"
              [disabled]="reloadFailed()"
              (click)="conflict.set(false)"
            >
              Revisé los cambios
            </button>
          </div>
        }
      </form></mat-dialog-content
    ><mat-dialog-actions align="end"
      ><button mat-button [mat-dialog-close]="false" [disabled]="saving()">Cancelar</button
      ><button
        mat-flat-button
        form="portfolio-edit"
        type="submit"
        [disabled]="
          form.invalid || form.pending || saving() || conflict() || !current().puede_editar
        "
      >
        {{ saving() ? 'Guardando…' : 'Guardar cambios' }}
      </button></mat-dialog-actions
    >`,
})
export class PortfolioEditDialog {
  private readonly data = inject<PortfolioDetail>(MAT_DIALOG_DATA);
  private readonly api = inject(PortfolioService);
  private readonly dialog = inject(MatDialogRef<PortfolioEditDialog>);
  readonly current = signal(this.data);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly conflict = signal(false);
  readonly reloadFailed = signal(false);
  readonly fieldError = fieldError;
  readonly form = inject(FormBuilder).nonNullable.group({
    nombre: [
      this.data.nombre,
      {
        validators: [Validators.required, trimmedName],
        asyncValidators: [this.api.nameValidator(this.data.id)],
      },
    ],
    descripcion: [this.data.descripcion, Validators.maxLength(500)],
    es_publico: [this.data.es_publico],
  });
  save() {
    if (
      this.form.invalid ||
      this.form.pending ||
      this.saving() ||
      this.conflict() ||
      !this.current().puede_editar
    )
      return;
    this.saving.set(true);
    this.error.set('');
    const value = this.form.getRawValue(),
      p = this.current();
    this.api
      .update(p.id, {
        version: p.version,
        nombre: value.nombre.trim(),
        descripcion: value.descripcion,
        ...(p.puede_cambiar_visibilidad ? { es_publico: value.es_publico } : {}),
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: () => this.dialog.close(true),
        error: (e) => {
          this.error.set(applyServerErrors(this.form, e));
          if (e instanceof HttpErrorResponse && e.status === 409) {
            this.conflict.set(true);
            this.reloadFailed.set(true);
            this.api.detail(p.id).subscribe({
              next: (updated) => {
                this.current.set(updated);
                this.reloadFailed.set(false);
              },
              error: () =>
                this.error.set(
                  'No se pudo recargar el portafolio. Cierra el formulario e intenta de nuevo.',
                ),
            });
          }
        },
      });
  }
}
