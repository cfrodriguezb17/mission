import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
@Component({
  imports: [RouterLink, MatButtonModule],
  template: `<main class="not-found">
    <span class="eyebrow">DATAPULSE LATAM</span>
    <p class="error-code">404</p>
    <h1>Esta página no está disponible</h1>
    <p>El enlace puede haber cambiado o la dirección no es correcta.</p>
    <a mat-flat-button routerLink="/dashboard">Ir al dashboard</a>
  </main>`,
})
export class NotFound {}
