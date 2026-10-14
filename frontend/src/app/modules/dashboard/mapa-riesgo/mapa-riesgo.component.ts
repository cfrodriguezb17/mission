import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DecimalPipe } from '@angular/common';
import { LATAM_PATHS } from '../../../shared/utils/latam-paths';
import { MapCountry } from '../../../core/models/api.models';
@Component({
  selector: 'app-risk-map',
  imports: [RouterLink, DecimalPipe],
  template: `<div class="map-container">
    <svg viewBox="0 0 520 420" role="group" aria-labelledby="mapTitle mapDesc">
      <title id="mapTitle">Mapa de riesgo de Latinoamérica</title>
      <desc id="mapDesc">
        Cada punto representa un país. Su color indica el riesgo IRPC. Los enlaces bajo el mapa
        ofrecen los mismos datos.
      </desc>
      <defs>
        <pattern id="grid" width="35" height="35" patternUnits="userSpaceOnUse">
          <path d="M35 0H0V35" fill="none" stroke="#e5eaf2" stroke-width=".7" />
        </pattern>
      </defs>
      <rect x="0" y="0" width="520" height="420" fill="url(#grid)" />
      <text x="35" y="255" class="ocean">OCÉANO PACÍFICO</text>
      <text x="365" y="135" class="ocean">OCÉANO ATLÁNTICO</text>
      @for (shape of shapes; track shape.code) {
        <path
          [attr.d]="shape.path"
          [attr.fill]="countryColor(shape.code)"
          stroke="white"
          stroke-width=".9"
          fill-rule="evenodd"
          opacity=".52"
        />
      }
      @for (country of countries(); track country.codigo_iso) {
        <a
          [routerLink]="['/paises', country.codigo_iso]"
          [attr.aria-label]="country.nombre + ', IRPC ' + (country.indice_compuesto ?? 'sin datos')"
        >
          <g>
            <circle
              [attr.cx]="x(country)"
              [attr.cy]="y(country)"
              r="11"
              [attr.fill]="country.color"
              opacity=".14"
            />
            <circle
              [attr.cx]="x(country)"
              [attr.cy]="y(country)"
              r="5.5"
              [attr.fill]="country.color"
              stroke="white"
              stroke-width="2"
            />
            <text [attr.x]="x(country) + 10" [attr.y]="y(country) + 3" class="map-label">
              {{ country.codigo_iso }}
            </text>
            <title>
              {{ country.nombre }} · IRPC {{ country.indice_compuesto ?? 'sin datos' }} ·
              {{ country.nivel_riesgo }}
            </title>
          </g>
        </a>
      }
    </svg>
    <div class="map-legend">
      <span><i style="background:#22c55e"></i>Bajo</span
      ><span><i style="background:#eab308"></i>Moderado</span
      ><span><i style="background:#f97316"></i>Alto</span
      ><span><i style="background:#ef4444"></i>Crítico</span
      ><span><i style="background:#94a3b8"></i>Sin datos</span>
    </div>
    <details>
      <summary>Explorar los países del mapa</summary>
      <ul>
        @for (country of countries(); track country.codigo_iso) {
          <li>
            <a [routerLink]="['/paises', country.codigo_iso]"
              >{{ country.nombre }} ·
              {{
                country.indice_compuesto === null
                  ? 'Sin datos'
                  : (country.indice_compuesto | number: '1.0-1')
              }}
              IRPC</a
            >
          </li>
        }
      </ul>
    </details>
  </div>`,
  styles: [
    `
      .map-container {
        background: #fafbfe;
        border-radius: 7px;
        overflow: hidden;
      }
      svg {
        width: 100%;
        height: 370px;
        display: block;
      }
      .land {
        fill: #e8edf5;
        stroke: #d2dbe8;
        stroke-width: 1.2;
        stroke-linejoin: round;
      }
      .borders {
        fill: none;
        stroke: #d2dbe8;
        stroke-width: 1;
      }
      .ocean {
        fill: #a3afc2;
        font-size: 8px;
        letter-spacing: 1.4px;
      }
      .map-label {
        fill: #4e5d78;
        font-size: 9px;
        font-weight: 600;
      }
      .map-legend {
        display: flex;
        justify-content: center;
        gap: 13px;
        flex-wrap: wrap;
        padding: 15px 8px;
        background: white;
        border-top: 1px solid #eef0f5;
        font-size: 9px;
        color: #65718a;
      }
      .map-legend span {
        display: flex;
        align-items: center;
        gap: 5px;
      }
      .map-legend i {
        width: 6px;
        height: 6px;
        border-radius: 50%;
      }
      details {
        font-size: 10px;
        padding: 10px 12px;
        color: #65718a;
        background: #fff;
      }
      summary {
        cursor: pointer;
      }
      ul {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        list-style: none;
        padding: 0;
      }
      a:focus circle {
        stroke: #17213b;
        stroke-width: 3;
      }
    `,
  ],
})
export class RiskMap {
  readonly countries = input<MapCountry[]>([]);
  readonly shapes = LATAM_PATHS;
  countryColor(code: string) {
    return this.countries().find((c) => c.codigo_iso === code)?.color ?? '#dce3ed';
  }
  x(c: MapCountry) {
    return ((Number(c.longitud) + 120) / 90) * 520;
  }
  y(c: MapCountry) {
    return ((35 - Number(c.latitud)) / 95) * 420;
  }
}
