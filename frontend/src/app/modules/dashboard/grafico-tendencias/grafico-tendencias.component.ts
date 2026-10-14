import { Component, input, output } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { Country, Trends, INDICATORS } from '../../../core/models/api.models';
import { DataChart, ChartSeries } from '../../../shared/charts/chart.component';
import { PageState } from '../../../shared/page-state/page-state.component';
export type TrendFilters = FormGroup<{ tipo: FormControl<string>; paises: FormControl<string[]> }>;
@Component({
  selector: 'app-grafico-tendencias',
  imports: [ReactiveFormsModule, MatFormFieldModule, MatSelectModule, DataChart, PageState],
  templateUrl: './grafico-tendencias.component.html',
  styles: [':host { display: contents; }'],
})
export class GraficoTendenciasComponent {
  readonly filters = input.required<TrendFilters>();
  readonly countries = input<Country[]>([]);
  readonly trends = input<Trends | null>(null);
  readonly trendLabels = input<string[]>([]);
  readonly trendSeries = input<ChartSeries[]>([]);
  readonly trendNotice = input(false);
  readonly trendLoading = input(false);
  readonly trendError = input(false);
  readonly indicators = INDICATORS;
  readonly retry = output<void>();
}
