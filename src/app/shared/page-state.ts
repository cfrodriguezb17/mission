import { Component, input, output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
@Component({
  selector: 'app-page-state',
  imports: [MatButtonModule, MatProgressSpinnerModule],
  template: `@if (loading()) {
      <div class="state" role="status">
        <mat-spinner diameter="30" />
        <p>Cargando información…</p>
      </div>
    } @else if (error()) {
      <div class="state" role="alert">
        <h3>No pudimos cargar la información</h3>
        <p>Comprueba la conexión con la API e intenta nuevamente.</p>
        <button mat-stroked-button (click)="retry.emit()">Reintentar</button>
      </div>
    } @else if (empty()) {
      <div class="state">
        <h3>{{ emptyTitle() }}</h3>
        <p>{{ emptyMessage() }}</p>
      </div>
    }`,
})
export class PageState {
  readonly loading = input(false);
  readonly error = input(false);
  readonly empty = input(false);
  readonly emptyTitle = input('Todavía no hay datos');
  readonly emptyMessage = input('Los datos aparecerán aquí cuando estén disponibles.');
  readonly retry = output<void>();
}
