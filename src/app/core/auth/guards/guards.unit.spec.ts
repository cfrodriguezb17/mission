import { TestBed } from '@angular/core/testing';
import {
  provideRouter,
  Router,
  ActivatedRouteSnapshot,
  RouterStateSnapshot,
} from '@angular/router';
import { firstValueFrom, Observable, of } from 'rxjs';
import { authGuard } from './auth.guard';
import { roleGuard } from './role.guard';
import { AuthService } from '../services/auth.service';
import { User } from '../../models/api.models';
describe('Protección de rutas', () => {
  let user: User | null;
  beforeEach(() => {
    user = null;
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: AuthService, useValue: { ensureUser: () => of(user) } },
      ],
    });
  });
  it('redirige al login conservando la ruta solicitada', async () => {
    const result = await firstValueFrom(
      TestBed.runInInjectionContext(() =>
        authGuard({} as ActivatedRouteSnapshot, { url: '/portafolios' } as RouterStateSnapshot),
      ) as Observable<unknown>,
    );
    expect(TestBed.inject(Router).serializeUrl(result as ReturnType<Router['createUrlTree']>)).toBe(
      '/login?returnUrl=%2Fportafolios',
    );
  });
  it.each(['ADMIN', 'ANALISTA'])('permite crear al rol %s', async (rol) => {
    user = { id: 1, email: 'a@b.com', nombre_completo: 'A', rol: rol as User['rol'], activo: true };
    const result = await firstValueFrom(
      TestBed.runInInjectionContext(() =>
        roleGuard(
          { data: { roles: ['ADMIN', 'ANALISTA'] } } as unknown as ActivatedRouteSnapshot,
          {} as RouterStateSnapshot,
        ),
      ) as Observable<unknown>,
    );
    expect(result).toBe(true);
  });
  it('bloquea a VIEWER aunque abra la URL directamente', async () => {
    user = { id: 1, email: 'a@b.com', nombre_completo: 'A', rol: 'VIEWER', activo: true };
    const result = await firstValueFrom(
      TestBed.runInInjectionContext(() =>
        roleGuard(
          { data: { roles: ['ADMIN', 'ANALISTA'] } } as unknown as ActivatedRouteSnapshot,
          {} as RouterStateSnapshot,
        ),
      ) as Observable<unknown>,
    );
    expect(TestBed.inject(Router).serializeUrl(result as ReturnType<Router['createUrlTree']>)).toBe(
      '/dashboard',
    );
  });
});
