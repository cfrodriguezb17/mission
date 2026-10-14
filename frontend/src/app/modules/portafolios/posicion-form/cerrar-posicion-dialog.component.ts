import { Component, inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { Position } from '../../../core/models/api.models';
import { localDate, isCalendarDate } from '../../../shared/utils/form-utils';
@Component({
  imports: [
    MatDialogModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
  ],
  template: `<h2 mat-dialog-title>Cerrar posición</h2>
    <mat-dialog-content
      ><p>
        La posición de {{ position.nombre_pais }} se conservará en el histórico y dejará de contar
        como capital activo.
      </p>
      <mat-form-field appearance="outline"
        ><mat-label>Fecha de salida</mat-label
        ><input matInput type="date" [formControl]="date" /><mat-error
          >Selecciona una fecha válida posterior al {{ position.fecha_entrada }}.</mat-error
        ></mat-form-field
      ></mat-dialog-content
    ><mat-dialog-actions align="end"
      ><button mat-button [mat-dialog-close]="null">Cancelar</button
      ><button mat-flat-button [disabled]="date.invalid" [mat-dialog-close]="date.value">
        Confirmar cierre
      </button></mat-dialog-actions
    >`,
})
export class ClosePositionDialog {
  readonly position = inject<Position>(MAT_DIALOG_DATA);
  readonly date = new FormControl(localDate(), {
    nonNullable: true,
    validators: [
      Validators.required,
      (control) =>
        isCalendarDate(String(control.value)) && String(control.value) > this.position.fecha_entrada
          ? null
          : { after: true },
    ],
  });
}
