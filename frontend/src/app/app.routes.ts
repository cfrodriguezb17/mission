import { Routes } from '@angular/router';
import { authGuard } from './core/auth/guards/auth.guard';
import { roleGuard } from './core/auth/guards/role.guard';
export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('./modules/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'registro',
    loadComponent: () =>
      import('./modules/auth/register/register.component').then((m) => m.RegisterComponent),
    data: { register: true },
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./layout/shell').then((m) => m.Shell),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./modules/dashboard/dashboard.component').then((m) => m.Dashboard),
      },
      {
        path: 'paises',
        loadComponent: () =>
          import('./modules/paises/lista-paises/lista-paises.component').then((m) => m.CountryList),
      },
      {
        path: 'paises/:codigo',
        loadComponent: () =>
          import('./modules/paises/detalle-pais/detalle-pais.component').then(
            (m) => m.CountryDetail,
          ),
      },
      {
        path: 'portafolios',
        loadComponent: () =>
          import('./modules/portafolios/lista/lista.component').then((m) => m.PortfolioList),
      },
      {
        path: 'portafolios/nuevo',
        canActivate: [roleGuard],
        data: { roles: ['ADMIN', 'ANALISTA'] },
        loadComponent: () =>
          import('./modules/portafolios/crear/crear.component').then((m) => m.PortfolioCreate),
      },
      {
        path: 'portafolios/:id',
        loadComponent: () =>
          import('./modules/portafolios/detalle/detalle.component').then(
            (m) => m.PortfolioDetailPage,
          ),
      },
      {
        path: 'alertas',
        loadComponent: () =>
          import('./modules/alertas/panel-alertas/panel-alertas.component').then(
            (m) => m.AlertsPage,
          ),
      },
      {
        path: 'perfil',
        loadComponent: () => import('./modules/perfil/perfil.component').then((m) => m.Profile),
      },
    ],
  },
  {
    path: '**',
    loadComponent: () => import('./shared/not-found/not-found.component').then((m) => m.NotFound),
  },
];
