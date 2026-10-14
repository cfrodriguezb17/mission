import { Component, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { Risk, label } from '../../../core/models/api.models';
import { RiskBadge } from '../../../shared/risk-badge/risk-badge.component';
import { PageState } from '../../../shared/page-state/page-state.component';
import { flag } from '../../../shared/utils/flags';
@Component({
  selector: 'app-tabla-ranking',
  imports: [DecimalPipe, RouterLink, MatIconModule, RiskBadge, PageState],
  templateUrl: './tabla-ranking.component.html',
  styles: [':host { display: contents; }'],
})
export class TablaRankingComponent {
  readonly ranking = input<Risk[]>([]);
  readonly flag = flag;
  readonly label = label;
  readonly number = Number;
}
