import { Component, input } from '@angular/core';
import { CatalogoPipe } from '../pipes/catalogo.pipe';
@Component({
  selector: 'app-risk-badge',
  imports: [CatalogoPipe],
  template: `<span class="risk-badge" [attr.data-risk]="level()">{{ level() | catalogo }}</span>`,
})
export class RiskBadge {
  readonly level = input('SIN_DATOS');
}
