import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';
import { AuthService } from './auth.service';
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService),
    router = inject(Router);
  return auth
    .ensureUser()
    .pipe(
      map((user) =>
        user ? true : router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } }),
      ),
    );
};
export const roleGuard: CanActivateFn = (route) => {
  const auth = inject(AuthService),
    router = inject(Router);
  return auth
    .ensureUser()
    .pipe(
      map((user) =>
        user && (route.data['roles'] as string[]).includes(user.rol)
          ? true
          : router.createUrlTree(['/dashboard']),
      ),
    );
};
