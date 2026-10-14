import { Component } from '@angular/core';
import { AuthForm } from '../auth-form/auth-form.component';
@Component({ imports: [AuthForm], template: '<app-auth-form />' })
export class LoginComponent {}
