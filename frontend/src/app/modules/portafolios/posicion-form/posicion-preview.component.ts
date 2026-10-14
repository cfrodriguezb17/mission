import { Component, computed, input, output } from '@angular/core';
import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { Country } from '../../../core/models/api.models';
import { PortfolioPreview } from './previsualizacion';

@Component({
  selector: 'app-position-preview',
  imports: [CurrencyPipe, DecimalPipe, MatButtonModule],
  template: `<section class="preview" aria-label="Previsualización del portafolio">
    <h3>Así quedaría tu portafolio</h3>
    @if (suspended()) {
      <p>No hay una estimación vigente hasta recargar el portafolio.</p>
    } @else if (preview(); as result) {
      <dl aria-live="polite" aria-atomic="true">
        <div>
          <dt>Total invertido activo</dt>
          <dd data-testid="preview-total">
            {{ result.total_invertido_usd | currency: 'USD' : 'symbol' : '1.2-2' }}
          </dd>
        </div>
        <div>
          <dt>IRPC ponderado</dt>
          <dd data-testid="preview-risk">
            @if (loading()) {
              Consultando índices…
            } @else if (error()) {
              No disponible
            } @else if (result.riesgo_promedio_ponderado === null) {
              Sin IRPC
            } @else {
              {{ result.riesgo_promedio_ponderado | number: '1.0-2' }} / 100
            }
          </dd>
        </div>
        <div>
          <dt>Posiciones activas</dt>
          <dd>{{ result.posiciones_activas }}</dd>
        </div>
      </dl>
      @if (error()) {
        <p>
          No pudimos cargar los índices. Puedes seguir editando; el riesgo se confirmará al guardar.
        </p>
        <button type="button" mat-button (click)="retry.emit()">Reintentar índices</button>
      } @else if (!loading()) {
        @if (result.riesgo_incompleto) {
          <p class="warning">
            Riesgo incompleto: {{ result.monto_sin_riesgo_usd | currency: 'USD' }} sin índice
            disponible ({{ missingCountries() }}). Ese capital no participa en el promedio.
          </p>
        }
        @if (result.contiene_simulaciones || result.datos_parciales) {
          <p>Algunos índices se basan en datos parciales o simulados.</p>
        }
      }
      <p class="footnote">
        Estimación con los índices consultados al abrir el formulario. Se confirmará al guardar. Un
        IRPC mayor indica menor riesgo.
      </p>
    } @else {
      <p>Selecciona un país y un monto válido para ver la estimación.</p>
    }
  </section>`,
  styles: [
    `
      :host {
        display: block;
      }
      .preview {
        padding: 16px;
        border: 1px solid #dfe3f1;
        border-radius: 12px;
        background: #f8faff;
        color: #26344c;
      }
      h3 {
        margin: 0 0 14px;
        font-size: 15px;
        font-weight: 700;
      }
      dl {
        display: grid;
        grid-template-columns: 1.3fr 1fr 0.7fr;
        gap: 14px;
        margin: 0 0 12px;
      }
      dt {
        font-size: 11px;
        color: #5f6d83;
        margin-bottom: 6px;
      }
      dd {
        margin: 0;
        font-size: 17px;
        font-weight: 700;
        overflow-wrap: anywhere;
      }
      p {
        margin: 8px 0 0;
        font-size: 12px;
        line-height: 1.6;
      }
      .footnote {
        color: #5f6d83;
      }
      .warning {
        color: #854d0e;
      }
      @media (max-width: 600px) {
        dl {
          grid-template-columns: 1fr;
          gap: 12px;
        }
      }
    `,
  ],
})
export class PositionPreviewComponent {
  readonly preview = input<PortfolioPreview | null>(null);
  readonly countries = input<Country[]>([]);
  readonly loading = input(false);
  readonly error = input(false);
  readonly suspended = input(false);
  readonly retry = output<void>();
  readonly missingCountries = computed(
    () =>
      this.preview()
        ?.paises_sin_riesgo.map(
          (code) => this.countries().find((country) => country.codigo_iso === code)?.nombre ?? code,
        )
        .join(', ') ?? '',
  );
}
