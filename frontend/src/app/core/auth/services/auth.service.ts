import { Service, inject, signal, computed } from '@angular/core';
import { HttpBackend, HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import {
  Observable,
  of,
  tap,
  switchMap,
  shareReplay,
  finalize,
  catchError,
  throwError,
  Subject,
  takeUntil,
  map,
} from 'rxjs';
import { ApiService } from '../../services/api.service';
import { Tokens, User } from '../../models/api.models';
@Service()
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly rawHttp = new HttpClient(inject(HttpBackend));
  private readonly router = inject(Router);
  readonly user = signal<User | null>(null);
  readonly canWrite = computed(() => !!this.user() && this.user()?.rol !== 'VIEWER');
  private readonly sessionEnded = new Subject<void>();
  private readonly accessChanged = new Subject<string | null>();
  readonly accessChanges$ = this.accessChanged.asObservable();
  private refreshRequest?: Observable<string>;
  get access(): string | null {
    return localStorage.getItem('datapulse.access');
  }
  get refreshToken(): string | null {
    return localStorage.getItem('datapulse.refresh');
  }
  login(email: string, password: string): Observable<User> {
    return this.api.post<Tokens>('/auth/login/', { email, password }).pipe(
      takeUntil(this.sessionEnded),
      tap((tokens) => {
        localStorage.setItem('datapulse.access', tokens.access);
        localStorage.setItem('datapulse.refresh', tokens.refresh);
        this.accessChanged.next(tokens.access);
      }),
      switchMap(() => this.loadProfile()),
      catchError((error) => {
        this.clear();
        return throwError(() => error);
      }),
    );
  }
  register(data: { email: string; nombre_completo: string; password: string }): Observable<User> {
    return this.api.post<User>('/auth/register/', data).pipe(
      takeUntil(this.sessionEnded),
      switchMap(() => this.login(data.email, data.password)),
    );
  }
  loadProfile(): Observable<User> {
    return this.storeProfile(this.api.get<User>('/auth/me/'));
  }
  ensureUser(): Observable<User | null> {
    return this.user()
      ? of(this.user())
      : this.access
        ? this.loadProfile().pipe(
            catchError(() => {
              this.clear();
              return of(null);
            }),
          )
        : of(null);
  }
  renew(): Observable<string> {
    if (!this.refreshRequest) {
      this.refreshRequest = this.rawHttp
        .post<{ access: string }>(this.api.base + '/auth/refresh/', { refresh: this.refreshToken })
        .pipe(
          takeUntil(this.sessionEnded),
          tap((t) => {
            localStorage.setItem('datapulse.access', t.access);
            this.accessChanged.next(t.access);
          }),
          map((t) => t.access),
          finalize(() => {
            this.refreshRequest = undefined;
          }),
          shareReplay({ bufferSize: 1, refCount: true }),
        );
    }
    return this.refreshRequest;
  }
  updateProfile(data: { email: string; nombre_completo: string; password?: string }) {
    return this.storeProfile(this.api.put<User>('/auth/me/', data));
  }
  private storeProfile(request: Observable<User>): Observable<User> {
    return request.pipe(
      takeUntil(this.sessionEnded),
      tap((user) => this.user.set(user)),
    );
  }
  clear(): void {
    this.sessionEnded.next();
    this.refreshRequest = undefined;
    localStorage.removeItem('datapulse.access');
    localStorage.removeItem('datapulse.refresh');
    this.user.set(null);
    this.accessChanged.next(null);
  }
  logout(): void {
    this.clear();
    void this.router.navigate(['/login']);
  }
}
