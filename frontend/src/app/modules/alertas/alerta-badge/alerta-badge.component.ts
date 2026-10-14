import { Component, inject, input } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatBadgeModule } from '@angular/material/badge';
import { AlertaService } from '../../../core/services/alerta.service';
@Component({
  selector: 'app-alerta-badge',
  imports: [AsyncPipe, RouterLink, MatButtonModule, MatIconModule, MatBadgeModule],
  template: `@if (alerts.summary$ | async; as summary) {
    @if (variant() === 'nav') {
      @if (summary.no_leidas) {
        <span class="nav-count">{{ summary.no_leidas }}</span>
      }
    } @else {
      <a
        mat-icon-button
        routerLink="/alertas"
        [attr.aria-label]="'Alertas, ' + summary.no_leidas + ' sin leer'"
        [matBadge]="summary.no_leidas"
        [matBadgeHidden]="!summary.no_leidas"
        matBadgeSize="small"
        ><mat-icon>notifications_none</mat-icon></a
      >
    }
  }`,
  styles: [':host { display: contents; }'],
})
export class AlertaBadgeComponent {
  readonly alerts = inject(AlertaService);
  readonly variant = input<'icon' | 'nav'>('icon');
}
