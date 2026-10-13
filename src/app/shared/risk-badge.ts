import { Component, input } from '@angular/core';
import { label } from '../core/models/api.models';
@Component({
  selector: 'app-risk-badge',
  template: `<span class="risk-badge" [attr.data-risk]="level()">{{ label(level()) }}</span>`,
})
export class RiskBadge {
  readonly level = input('SIN_DATOS');
  readonly label = label;
}
