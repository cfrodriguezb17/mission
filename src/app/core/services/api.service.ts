import { Service, inject } from '@angular/core';
import { HttpClient, HttpContext, HttpContextToken } from '@angular/common/http';
import { Observable, expand, reduce, EMPTY } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Page, Params } from '../models/api.models';
export const SILENT = new HttpContextToken<boolean>(() => false);
@Service()
export class ApiService {
  private readonly http = inject(HttpClient);
  readonly base = environment.apiBaseUrl.replace(/\/$/, '');
  get<T>(path: string, params: Params = {}, silent = false): Observable<T> {
    return this.http.get<T>(this.base + path, {
      params: this.params(params),
      context: new HttpContext().set(SILENT, silent),
    });
  }
  all<T>(path: string, params: Params = {}, silent = false): Observable<T[]> {
    // Follow every page without trusting a server-supplied host for authenticated requests.
    const page = (n: number) =>
      this.get<Page<T>>(path, { ...params, page_size: 100, page: n }, silent);
    return page(1).pipe(
      expand((result, index) => (result.next ? page(index + 2) : EMPTY)),
      reduce((all: T[], result) => [...all, ...result.results], []),
    );
  }
  post<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(this.base + path, body);
  }
  put<T>(path: string, body: unknown): Observable<T> {
    return this.http.put<T>(this.base + path, body);
  }
  delete<T>(path: string, body: unknown): Observable<T> {
    return this.http.delete<T>(this.base + path, { body });
  }
  download(path: string) {
    return this.http.get(this.base + path, { responseType: 'blob', observe: 'response' });
  }
  private params(values: Params): Record<string, string> {
    return Object.fromEntries(
      Object.entries(values)
        .filter(([, v]) => v !== undefined && v !== '')
        .map(([k, v]) => [k, String(v)]),
    );
  }
}
