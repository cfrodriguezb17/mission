import { Component, input } from '@angular/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
@Component({
  selector: 'app-loading-spinner',
  imports: [MatProgressSpinnerModule, MatProgressBarModule],
  template: `@if (variant() === 'bar') {
      <mat-progress-bar mode="indeterminate" aria-label="Cargando solicitudes" />
    } @else {
      <div class="state" role="status">
        <mat-spinner diameter="30" />
        <p>Cargando información…</p>
      </div>
    }`,
  styles: [':host { display: contents; }'],
})
export class LoadingSpinnerComponent {
  readonly variant = input<'spinner' | 'bar'>('spinner');
}
