import { Component, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { DashboardSummary } from '../../../core/models/api.models';
@Component({
  selector: 'app-kpi-cards',
  imports: [DecimalPipe, RouterLink, MatIconModule],
  templateUrl: './kpi-cards.component.html',
  styles: [':host { display: contents; }'],
})
export class KpiCardsComponent {
  readonly summary = input.required<DashboardSummary>();
}
