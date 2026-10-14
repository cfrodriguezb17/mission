import { Component, ElementRef, viewChild, input, effect, DestroyRef, inject } from '@angular/core';
import { Chart, registerables, ChartDataset } from 'chart.js';
Chart.register(...registerables);
export interface ChartSeries {
  label: string;
  values: (number | null)[];
  color?: string;
}
@Component({
  selector: 'app-chart',
  template: `<div class="chart-wrap" role="img" [attr.aria-label]="title()">
      <canvas #canvas aria-hidden="true"></canvas>
    </div>
    <details class="chart-data">
      <summary>Ver datos de {{ title().toLowerCase() }}</summary>
      <div class="table-scroll">
        <table>
          <caption class="sr-only">
            {{
              title()
            }}
          </caption>
          <thead>
            <tr>
              <th scope="col">Período / categoría</th>
              @for (s of series(); track s.label) {
                <th scope="col">{{ s.label }}</th>
              }
            </tr>
          </thead>
          <tbody>
            @for (x of labels(); track $index; let i = $index) {
              <tr>
                <th scope="row">{{ x }}</th>
                @for (s of series(); track s.label) {
                  <td>{{ s.values[i] ?? 'Sin datos' }}</td>
                }
              </tr>
            }
          </tbody>
        </table>
      </div>
    </details>`,
  styles: [
    `
      .chart-wrap {
        height: 265px;
        position: relative;
        width: 100%;
      }
      details {
        margin-top: 16px;
        font-size: 12px;
        color: #53627a;
      }
      summary {
        cursor: pointer;
      }
      table {
        margin-top: 12px;
      }
    `,
  ],
})
export class DataChart {
  readonly canvas = viewChild<ElementRef<HTMLCanvasElement>>('canvas');
  readonly labels = input<string[]>([]);
  readonly series = input<ChartSeries[]>([]);
  readonly title = input('Gráfico');
  readonly type = input<'line' | 'pie' | 'doughnut'>('line');
  private chart?: Chart;
  constructor() {
    effect(() => {
      const canvas = this.canvas();
      const labels = this.labels(),
        series = this.series(),
        type = this.type();
      if (!canvas) return;
      this.chart?.destroy();
      const palette = [
        '#4f46e5',
        '#0d9488',
        '#b45309',
        '#ec4899',
        '#6366f1',
        '#0891b2',
        '#4d7c0f',
        '#c2410c',
        '#8b5cf6',
        '#64748b',
      ];
      const datasets: ChartDataset[] = series.map((s, i) => ({
        label: s.label,
        data: s.values,
        borderColor: s.color ?? palette[i % palette.length],
        backgroundColor: type === 'line' ? (s.color ?? palette[i % palette.length]) : palette,
        borderWidth: type === 'line' ? 2.5 : 2,
        pointRadius: 3,
        tension: 0.32,
        spanGaps: false,
      }));
      this.chart = new Chart(canvas.nativeElement, {
        type,
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom',
              labels: {
                usePointStyle: true,
                boxWidth: 8,
                padding: 20,
                font: { family: 'Inter, Arial', size: 11 },
              },
            },
          },
          ...(type === 'line'
            ? {
                scales: {
                  x: { grid: { display: false }, ticks: { color: '#64748b' } },
                  y: { grid: { color: '#edf0f5' }, ticks: { color: '#64748b' } },
                },
              }
            : {}),
        },
      });
    });
    inject(DestroyRef).onDestroy(() => this.chart?.destroy());
  }
}
