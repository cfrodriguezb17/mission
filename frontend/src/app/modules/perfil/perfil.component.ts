import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatButtonModule } from '@angular/material/button';
import { finalize } from 'rxjs';
import { AuthService } from '../../core/auth/services/auth.service';
import { NotifyService } from '../../core/services/notify.service';
import { applyServerErrors, fieldError } from '../../shared/utils/form-utils';
@Component({
  imports: [ReactiveFormsModule, MatInputModule, MatFormFieldModule, MatButtonModule],
  template: `<div class="page-heading">
      <div>
        <span class="eyebrow">MI CUENTA</span>
        <h1>Mi perfil</h1>
        <p>Actualiza tu información personal y contraseña.</p>
      </div>
    </div>
    <section class="panel form-panel">
      <div class="panel-heading">
        <h2>Información personal</h2>
        <span class="pill">{{ auth.user()?.rol }}</span>
      </div>
      <form [formGroup]="form" (ngSubmit)="save()">
        <mat-form-field appearance="outline"
          ><mat-label>Nombre completo</mat-label
          ><input matInput formControlName="nombre_completo" autocomplete="name" /><mat-error>{{
            fieldError(form.controls.nombre_completo)
          }}</mat-error></mat-form-field
        ><mat-form-field appearance="outline"
          ><mat-label>Correo electrónico</mat-label
          ><input matInput formControlName="email" type="email" autocomplete="email" /><mat-error>{{
            fieldError(form.controls.email)
          }}</mat-error></mat-form-field
        ><mat-form-field appearance="outline"
          ><mat-label>Nueva contraseña (opcional)</mat-label
          ><input
            matInput
            formControlName="password"
            type="password"
            autocomplete="new-password"
          /><mat-hint
            >Déjala vacía para conservar la actual. Al cambiarla se cerrará la sesión.</mat-hint
          ><mat-error>{{ fieldError(form.controls.password) }}</mat-error></mat-form-field
        >
        @if (error()) {
          <p class="form-error" role="alert">{{ error() }}</p>
        }
        <div class="form-actions">
          <button mat-flat-button [disabled]="form.invalid || saving()">
            {{ saving() ? 'Guardando…' : 'Guardar cambios' }}
          </button>
        </div>
      </form>
    </section>`,
})
export class Profile {
  readonly auth = inject(AuthService);
  private readonly notify = inject(NotifyService);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly fieldError = fieldError;
  readonly form = inject(FormBuilder).nonNullable.group({
    email: [this.auth.user()?.email ?? '', [Validators.required, Validators.email]],
    nombre_completo: [
      this.auth.user()?.nombre_completo ?? '',
      [Validators.required, Validators.pattern(/\S/)],
    ],
    password: ['', Validators.minLength(6)],
  });
  save() {
    if (this.form.invalid || this.saving()) return;
    const value = this.form.getRawValue();
    this.saving.set(true);
    this.error.set('');
    this.auth
      .updateProfile({
        email: value.email,
        nombre_completo: value.nombre_completo,
        ...(value.password ? { password: value.password } : {}),
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: () => {
          this.notify.show('Perfil actualizado.');
          if (value.password) this.auth.logout();
        },
        error: (e) => this.error.set(applyServerErrors(this.form, e)),
      });
  }
}
