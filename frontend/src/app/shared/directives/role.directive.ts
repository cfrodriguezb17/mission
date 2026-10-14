import { Directive, effect, inject, input, TemplateRef, ViewContainerRef } from '@angular/core';
import { AuthService } from '../../core/auth/services/auth.service';
import { Role } from '../../core/models/api.models';
@Directive({ selector: '[appRole]' })
export class RoleDirective {
  readonly appRole = input.required<readonly Role[]>();
  private readonly auth = inject(AuthService);
  private readonly template = inject(TemplateRef<unknown>);
  private readonly container = inject(ViewContainerRef);
  constructor() {
    effect(() => {
      const user = this.auth.user();
      const allowed = !!user && this.appRole().includes(user.rol);
      if (allowed && this.container.length === 0) this.container.createEmbeddedView(this.template);
      else if (!allowed) this.container.clear();
    });
  }
}
