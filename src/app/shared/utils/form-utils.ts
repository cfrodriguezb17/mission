import { AbstractControl, FormGroup, ValidationErrors, ValidatorFn } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
export const trimmedName: ValidatorFn = (control) => {
  const value = String(control.value ?? '').trim();
  return value.length < 3 ? { trimmed: true } : value.length > 100 ? { maxlength: true } : null;
};
export function localDate(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
export function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000-')) return false;
  const date = new Date(value + 'T00:00:00Z');
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}
export const notFuture: ValidatorFn = (control) => {
  const value = String(control.value ?? '');
  return !isCalendarDate(value) || value > localDate() ? { date: true } : null;
};
// Integer cents keep business validation exact without rounding money through floats.
export function cents(value: string): bigint | null {
  if (!/^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?$/.test(value.trim())) return null;
  const text = value.replaceAll(',', '').trim();
  const [whole, fraction = ''] = text.split('.');
  return BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
}
export const moneyValidator: ValidatorFn = (control) => {
  const amount = cents(String(control.value ?? ''));
  return amount === null
    ? { money: true }
    : amount < 100000n || amount > 1000000000n
      ? { range: true }
      : null;
};
export function fieldError(control: AbstractControl | null): string {
  if (!control || !(control.touched || control.dirty)) return '';
  const errors: ValidationErrors = control.errors ?? {};
  if (errors['server']) return String(errors['server']);
  if (errors['required']) return 'Este campo es obligatorio.';
  if (errors['email']) return 'Ingresa un correo electrónico válido.';
  if (errors['trimmed']) return 'Usa entre 3 y 100 caracteres, sin contar espacios extremos.';
  if (errors['minlength']) return `Usa al menos ${errors['minlength'].requiredLength} caracteres.`;
  if (errors['maxlength']) return 'Superaste el máximo de caracteres permitidos.';
  if (errors['duplicate']) return 'Ya existe un portafolio con este nombre.';
  if (errors['availability'])
    return 'No se pudo verificar el nombre. Modifícalo o vuelve a comprobarlo.';
  if (errors['money'])
    return 'Ingresa un monto válido con un máximo de dos decimales (ej. 1,000.00).';
  if (errors['range']) return 'El monto debe estar entre 1,000 y 10,000,000 USD.';
  if (errors['date']) return 'Selecciona una fecha válida que no sea futura.';
  if (errors['pattern']) return 'Ingresa un valor válido, sin dejar solo espacios.';
  if (errors['country']) return 'Selecciona un país de la lista.';
  return '';
}
export function applyServerErrors(form: FormGroup, error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) return 'No se pudo completar la operación.';
  const body = error.error as Record<string, unknown> | null;
  if (body)
    for (const [key, value] of Object.entries(body)) {
      const control = form.get(key);
      if (control) {
        control.setErrors({ server: Array.isArray(value) ? value.join(' ') : String(value) });
        control.markAsTouched();
      }
    }
  const detail = body?.['error'] as { mensaje?: string } | undefined;
  return error.status === 409
    ? 'Hay cambios de otro usuario. Revisa los datos actualizados antes de volver a guardar.'
    : (detail?.mensaje ?? 'No se pudo guardar. Revisa los campos y tu conexión.');
}
