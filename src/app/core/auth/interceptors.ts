import { inject } from '@angular/core';
import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, switchMap, throwError, finalize, from } from 'rxjs';
import { AuthService } from './auth.service';
import { NotifyService } from '../services/notify.service';
import { LoadingService } from '../services/loading.service';
import { SILENT } from '../services/api.service';
import { environment } from '../../../environments/environment';
function isApi(url: string): boolean {
  return url.startsWith(environment.apiBaseUrl.replace(/\/$/, '') + '/');
}
export const jwtInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService),
    notify = inject(NotifyService);
  const protectedRequest =
    isApi(request.url) && !/\/auth\/(login|register|refresh)\/$/.test(request.url);
  if (!protectedRequest) return next(request);
  const originalToken = auth.access;
  const withToken = (token: string | null) =>
    request.clone({ setHeaders: token ? { Authorization: 'Bearer ' + token } : {} });
  const expire = () => {
    if (auth.access) {
      notify.show('Tu sesión expiró. Inicia sesión nuevamente.');
      auth.logout();
    }
  };
  return next(withToken(originalToken)).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse) || error.status !== 401)
        return throwError(() => error);
      if (!auth.refreshToken) {
        expire();
        return throwError(() => error);
      }
      // A late 401 may belong to a token that another request already renewed.
      const renewal =
        auth.access !== originalToken && auth.access ? from([auth.access]) : auth.renew();
      return renewal.pipe(
        catchError((failure: unknown) => {
          expire();
          return throwError(() => failure);
        }),
        switchMap((token) =>
          next(withToken(token)).pipe(
            catchError((failure: unknown) => {
              if (failure instanceof HttpErrorResponse && failure.status === 401) expire();
              return throwError(() => failure);
            }),
          ),
        ),
      );
    }),
  );
};
export const loadingInterceptor: HttpInterceptorFn = (request, next) => {
  const loading = inject(LoadingService);
  if (request.context.get(SILENT)) return next(request);
  loading.start();
  return next(request).pipe(finalize(() => loading.stop()));
};
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
