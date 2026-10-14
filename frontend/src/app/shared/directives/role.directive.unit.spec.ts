import { Component, input, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { RoleDirective } from './role.directive';
import { AuthService } from '../../core/auth/services/auth.service';
import { Role, User } from '../../core/models/api.models';

@Component({
  imports: [RoleDirective],
  template: `<button *appRole="roles()">Sincronizar indicadores</button>`,
})
class RoleHost {
  readonly roles = input<readonly Role[]>(['ADMIN']);
}

describe('Visibilidad de acciones según el rol', () => {
  const user = signal<User | null>(null);
  function setup() {
    user.set(null);
    TestBed.configureTestingModule({
      imports: [RoleHost],
      providers: [{ provide: AuthService, useValue: { user } }],
    });
    return TestBed.createComponent(RoleHost);
  }
  function setRole(rol: Role) {
    user.set({ id: 1, email: 'test@example.com', nombre_completo: 'Usuario', rol, activo: true });
  }
  it('actualiza las acciones al iniciar sesión, cambiar de rol y cerrar sesión', () => {
    const fixture = setup();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
    setRole('ADMIN');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Sincronizar indicadores');
    setRole('ANALISTA');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
    setRole('ADMIN');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('button')).toHaveLength(1);
    user.set(null);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
  });
  it('respeta los roles configurados y los cambios de esa configuración', () => {
    const fixture = setup();
    fixture.componentRef.setInput('roles', ['ADMIN', 'ANALISTA']);
    setRole('ANALISTA');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('button')).toHaveLength(1);
    setRole('VIEWER');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
    fixture.componentRef.setInput('roles', ['VIEWER']);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('button')).toHaveLength(1);
  });
});
