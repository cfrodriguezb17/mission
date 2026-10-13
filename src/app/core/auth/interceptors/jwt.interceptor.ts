import { inject } from '@angular/core';
import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, switchMap, throwError, from } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { NotifyService } from '../../services/notify.service';
import { environment } from '../../../../environments/environment';
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
