import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';
import { AuthService } from '../services/auth.service';
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
