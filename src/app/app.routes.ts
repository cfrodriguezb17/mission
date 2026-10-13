import { Routes } from '@angular/router';
import { authGuard, roleGuard } from './core/auth/guards';
export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/auth/auth-page').then((m) => m.AuthPage),
  },
  {
    path: 'registro',
    loadComponent: () => import('./features/auth/auth-page').then((m) => m.AuthPage),
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
        loadComponent: () => import('./features/dashboard/dashboard').then((m) => m.Dashboard),
      },
      {
        path: 'paises',
        loadComponent: () => import('./features/countries/country-list').then((m) => m.CountryList),
      },
      {
        path: 'paises/:codigo',
        loadComponent: () =>
          import('./features/countries/country-detail').then((m) => m.CountryDetail),
      },
      {
        path: 'portafolios',
        loadComponent: () =>
          import('./features/portfolios/portfolio-list').then((m) => m.PortfolioList),
      },
      {
        path: 'portafolios/nuevo',
        canActivate: [roleGuard],
        data: { roles: ['ADMIN', 'ANALISTA'] },
        loadComponent: () =>
          import('./features/portfolios/portfolio-create').then((m) => m.PortfolioCreate),
      },
      {
        path: 'portafolios/:id',
        loadComponent: () =>
          import('./features/portfolios/portfolio-detail').then((m) => m.PortfolioDetailPage),
      },
      {
        path: 'alertas',
        loadComponent: () => import('./features/alerts/alerts-page').then((m) => m.AlertsPage),
      },
      {
        path: 'perfil',
        loadComponent: () => import('./features/profile/profile').then((m) => m.Profile),
      },
    ],
  },
  { path: '**', loadComponent: () => import('./shared/not-found').then((m) => m.NotFound) },
];
