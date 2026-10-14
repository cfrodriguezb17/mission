import { Component, input } from '@angular/core';
import { DataChart, ChartSeries } from '../../../shared/charts/chart.component';
@Component({
  selector: 'app-distribucion-chart',
  imports: [DataChart],
  template: `<section class="panel">
    <div class="panel-heading">
      <h2>{{ title() }}</h2>
      <span class="pill">Capital activo</span>
    </div>
    <app-chart
      [type]="type()"
      [title]="chartTitle() || title()"
      [labels]="labels()"
      [series]="series()"
    />
  </section>`,
  styles: [':host { display: contents; }'],
})
export class DistribucionChartComponent {
  readonly title = input.required<string>();
  readonly chartTitle = input('');
  readonly type = input<'pie' | 'doughnut'>('pie');
  readonly labels = input<string[]>([]);
  readonly series = input<ChartSeries[]>([]);
}
