import { inject } from '@angular/core';
import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, switchMap, throwError, from } from 'rxjs';
import { NotifyService } from '../services/notify.service';
import { SILENT } from '../services/api.service';
export const errorInterceptor: HttpInterceptorFn = (request, next) => {
  const notify = inject(NotifyService);
  return next(request).pipe(
    catchError((error: HttpErrorResponse) => {
      const report = (value: unknown) => {
        const payload = value as { error?: { mensaje?: string } } | null;
        const retry = error.headers?.get('Retry-After');
        const message =
          error.status === 0
            ? 'No se pudo conectar con el servidor. Comprueba tu conexión e intenta de nuevo.'
            : error.status === 429
              ? `Demasiadas solicitudes. Intenta de nuevo ${retry ? 'en ' + retry + ' segundos' : 'más tarde'}.`
              : error.status === 409
                ? 'Este portafolio cambió mientras lo editabas. Se actualizaron los datos; revisa tu formulario antes de guardar.'
                : (payload?.error?.mensaje ?? 'No se pudo completar la operación.');
        if (!request.context.get(SILENT) && error.status !== 401) notify.show(message);
        return throwError(
          () =>
            new HttpErrorResponse({
              error: value,
              status: error.status,
              statusText: error.statusText,
              headers: error.headers,
              url: error.url ?? undefined,
            }),
        );
      };
      if (error.error instanceof Blob)
        return from(error.error.text()).pipe(
          switchMap((text) => {
            let value: unknown;
            try {
              value = JSON.parse(text);
            } catch {
              value = null;
            }
            return report(value);
          }),
        );
      return report(error.error as unknown);
    }),
  );
};
