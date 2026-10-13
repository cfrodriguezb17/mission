import { Component, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormBuilder, ReactiveFormsModule, Validators, ValidatorFn } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { finalize } from 'rxjs';
import { PortfolioDetail, Position, Country, ASSETS } from '../../core/models/api.models';
import { PortfolioService } from '../../core/services/portfolio.service';
import {
  fieldError,
  moneyValidator,
  notFuture,
  isCalendarDate,
  cents,
  localDate,
  applyServerErrors,
} from '../../shared/form-utils';
export interface PositionDialogData {
  portfolio: PortfolioDetail;
  position?: Position;
  countries: Country[];
}
@Component({
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatAutocompleteModule,
    MatButtonModule,
  ],
  templateUrl: './position-dialog.html',
})
export class PositionDialog {
  readonly data = inject<PositionDialogData>(MAT_DIALOG_DATA);
  private readonly api = inject(PortfolioService);
  private readonly dialog = inject(MatDialogRef<PositionDialog>);
  readonly current = signal(this.data.portfolio);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly conflict = signal(false);
  readonly reloadFailed = signal(false);
  readonly fieldError = fieldError;
  readonly assets = ASSETS;
  readonly today = localDate();
  private readonly countryValidator: ValidatorFn = (control) =>
    this.data.countries.some((c) => c.codigo_iso === control.value) ? null : { country: true };
  private readonly crossValidator: ValidatorFn = (control) => {
    const value = control.value as {
      pais: string;
      tipo_activo: string;
      monto_inversion_usd: string;
      fecha_entrada: string;
      fecha_salida: string;
    };
    const country = this.data.countries.find((c) => c.codigo_iso === value.pais);
    if (value.tipo_activo === 'MONEDA' && country?.moneda_codigo === 'USD')
      return { cross: 'No puedes invertir en MONEDA para un país cuya moneda principal es USD.' };
    if (
      value.fecha_salida &&
      (!isCalendarDate(value.fecha_salida) || value.fecha_salida <= value.fecha_entrada)
    )
      return { cross: 'La fecha de salida debe ser posterior a la entrada.' };
    const active = this.current().posiciones.filter(
      (p) => !p.fecha_salida && p.id !== this.data.position?.id,
    );
    if (
      !value.fecha_salida &&
      active.filter((p) => p.pais === value.pais && p.tipo_activo === value.tipo_activo).length >= 2
    )
      return { cross: 'Ya existen dos posiciones activas de este tipo en el país.' };
    const amount = cents(value.monto_inversion_usd);
    if (
      amount !== null &&
      !value.fecha_salida &&
      active.reduce((sum, p) => sum + (cents(p.monto_inversion_usd) ?? 0n), amount) > 5000000000n
    )
      return { cross: 'El capital activo del portafolio no puede superar 50,000,000 USD.' };
    return null;
  };
  readonly form = inject(FormBuilder).nonNullable.group(
    {
      pais: [this.data.position?.pais ?? '', [Validators.required, this.countryValidator]],
      tipo_activo: [this.data.position?.tipo_activo ?? '', [Validators.required]],
      monto_inversion_usd: [
        this.data.position?.monto_inversion_usd ?? '',
        [Validators.required, moneyValidator],
      ],
      fecha_entrada: [
        this.data.position?.fecha_entrada ?? this.today,
        [Validators.required, notFuture],
      ],
      fecha_salida: [this.data.position?.fecha_salida ?? ''],
      notas: [this.data.position?.notas ?? '', Validators.maxLength(200)],
    },
    { validators: this.crossValidator },
  );
  displayCountry = (code: string) =>
    this.data.countries.find((c) => c.codigo_iso === code)?.nombre ?? code;
  filteredCountries() {
    const query = this.form.controls.pais.value.toLowerCase();
    return this.data.countries.filter(
      (c) => c.nombre.toLowerCase().includes(query) || c.codigo_iso.toLowerCase().includes(query),
    );
  }
  formatAmount() {
    const c = this.form.controls.monto_inversion_usd;
    const amount = cents(c.value);
    if (amount !== null) {
      const text = (amount / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
      c.setValue(text + '.' + (amount % 100n).toString().padStart(2, '0'));
    }
  }
  save() {
    if (this.form.invalid || this.saving() || this.conflict() || !this.current().puede_editar) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.error.set('');
    const v = this.form.getRawValue(),
      p = this.current();
    this.api
      .savePosition(p.id, this.data.position?.id ?? null, {
        ...v,
        version: p.version,
        monto_inversion_usd: v.monto_inversion_usd.replaceAll(',', ''),
        fecha_salida: v.fecha_salida || null,
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
                this.form.updateValueAndValidity();
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
