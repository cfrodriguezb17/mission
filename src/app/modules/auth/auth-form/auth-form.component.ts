import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { finalize } from 'rxjs';
import { AuthService } from '../../../core/auth/services/auth.service';
import { applyServerErrors, fieldError } from '../../../shared/utils/form-utils';
@Component({
  selector: 'app-auth-form',
  imports: [
    RouterLink,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './auth-form.component.html',
})
export class AuthForm {
  readonly register = !!inject(ActivatedRoute).snapshot.data['register'];
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly hide = signal(true);
  readonly fieldError = fieldError;
  readonly form = inject(FormBuilder).nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    nombre_completo: ['', this.register ? [Validators.required, Validators.pattern(/\S/)] : []],
    password: ['', [Validators.required, ...(this.register ? [Validators.minLength(6)] : [])]],
  });
  submit() {
    if (this.form.invalid || this.saving()) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.error.set('');
    const value = this.form.getRawValue();
    const request = this.register
      ? this.auth.register(value)
      : this.auth.login(value.email, value.password);
    request.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        const target = this.route.snapshot.queryParamMap.get('returnUrl');
        void this.router.navigateByUrl(
          target?.startsWith('/') && !target.startsWith('//') ? target : '/dashboard',
        );
      },
      error: (error) => this.error.set(applyServerErrors(this.form, error)),
    });
  }
}
