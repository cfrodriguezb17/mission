import { FormControl, FormGroup } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import {
  cents,
  moneyValidator,
  notFuture,
  trimmedName,
  applyServerErrors,
  localDate,
} from './form-utils';
describe('Validaciones de negocio', () => {
  it('conserva centavos y montos grandes sin redondear', () => {
    expect(cents('10,000,000.01')).toBe(1000000001n);
    expect(cents('0.10')).toBe(10n);
    expect(cents('1000.001')).toBeNull();
  });
  it.each(['1000', '1,000.01', '10000000.00'])('acepta el monto permitido %s', (value) => {
    expect(moneyValidator(new FormControl(value))).toBeNull();
  });
  it.each(['999.99', '10000000.01', '-1000', '1e6', 'NaN', '1000.001'])(
    'rechaza el monto inválido %s',
    (value) => {
      expect(moneyValidator(new FormControl(value))).toBeTruthy();
    },
  );
  it('valida el nombre después de recortar espacios', () => {
    expect(trimmedName(new FormControl('  ab  '))).toEqual({ trimmed: true });
    expect(trimmedName(new FormControl('  Latam  '))).toBeNull();
  });
  it('rechaza fechas futuras y acepta hoy', () => {
    expect(notFuture(new FormControl('9999-01-01'))).toBeTruthy();
    expect(notFuture(new FormControl(localDate()))).toBeNull();
  });
  it.each(['2025-02-29', '2024-02-30', '2025-04-31', '2025-00-10', '2025-13-01', '2025-01-00'])(
    'RGR fecha: rechaza la fecha imposible %s',
    (value) => expect(notFuture(new FormControl(value))).toEqual({ date: true }),
  );
  it.each(['2024-02-29', '2000-02-29'])('RGR fecha: acepta el día bisiesto válido %s', (value) =>
    expect(notFuture(new FormControl(value))).toBeNull(),
  );
  it('presenta los errores de campo del backend', () => {
    const form = new FormGroup({ nombre: new FormControl('Latam') });
    applyServerErrors(
      form,
      new HttpErrorResponse({
        status: 400,
        error: { nombre: ['Nombre ocupado.'], error: { mensaje: 'Revise los datos.' } },
      }),
    );
    expect(form.controls.nombre.errors?.['server']).toBe('Nombre ocupado.');
    expect(form.controls.nombre.touched).toBe(true);
  });
});
