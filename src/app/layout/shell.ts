import { Component, inject, DestroyRef, signal } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { Title } from '@angular/platform-browser';
import { A11yModule } from '@angular/cdk/a11y';
import { AsyncPipe } from '@angular/common';
import { RouterLink, RouterLinkActive, RouterOutlet, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatBadgeModule } from '@angular/material/badge';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { AuthService } from '../core/auth/auth.service';
import { AlertService } from '../core/services/alert.service';
import { LoadingService } from '../core/services/loading.service';
@Component({
  imports: [
    A11yModule,
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    AsyncPipe,
    MatButtonModule,
    MatIconModule,
    MatBadgeModule,
    MatMenuModule,
    MatProgressBarModule,
  ],
  templateUrl: './shell.html',
  host: { '(document:keydown.escape)': 'menuOpen.set(false)' },
})
export class Shell {
  readonly auth = inject(AuthService);
  readonly alerts = inject(AlertService);
  readonly loading = inject(LoadingService);
  readonly menuOpen = signal(false);
  readonly page = signal('Vista general');
  readonly links = [
    { path: '/dashboard', icon: 'space_dashboard', label: 'Dashboard', group: 'ANÁLISIS' },
    { path: '/paises', icon: 'public', label: 'Países y mercados', group: '' },
    { path: '/portafolios', icon: 'work_outline', label: 'Portafolios', group: '' },
    {
      path: '/alertas',
      icon: 'notifications_none',
      label: 'Centro de alertas',
      group: 'SEGUIMIENTO',
    },
  ];
  constructor() {
    const router = inject(Router),
      document = inject(DOCUMENT),
      title = inject(Title);
    const update = () => {
      this.page.set(this.links.find((x) => router.url.startsWith(x.path))?.label ?? 'Mi perfil');
      this.menuOpen.set(false);
      title.setTitle(this.page() + ' · DataPulse Latam');
      setTimeout(() => document.getElementById('main-content')?.focus({ preventScroll: true }));
    };
    update();
    router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(update);
    this.alerts.start();
    inject(DestroyRef).onDestroy(() => this.alerts.stop());
  }
  initials() {
    return (
      this.auth
        .user()
        ?.nombre_completo.split(' ')
        .filter(Boolean)
        .slice(0, 2)
        .map((x) => x[0])
        .join('')
        .toUpperCase() ?? 'DP'
    );
  }
}
