import { Service, inject } from '@angular/core';
import { map, catchError, of, timer, switchMap } from 'rxjs';
import { AsyncValidatorFn } from '@angular/forms';
import { ApiService } from './api.service';
import {
  Portfolio,
  PortfolioDetail,
  PortfolioSummary,
  Position,
  Page,
  Params,
} from '../models/api.models';
@Service()
export class PortfolioService {
  private readonly api = inject(ApiService);
  list(params: Params = {}) {
    return this.api.get<Page<Portfolio>>('/portafolios/', params);
  }
  detail(id: number) {
    return this.api.get<PortfolioDetail>(`/portafolios/${id}/`);
  }
  summary(id: number) {
    return this.api.get<PortfolioSummary>(`/portafolios/${id}/resumen/`);
  }
  create(body: unknown) {
    return this.api.post<Portfolio>('/portafolios/', body);
  }
  update(id: number, body: unknown) {
    return this.api.put<Portfolio>(`/portafolios/${id}/`, body);
  }
  remove(id: number, version: number) {
    return this.api.delete<void>(`/portafolios/${id}/`, { version });
  }
  savePosition(id: number, position: number | null, body: unknown) {
    const path = `/portafolios/${id}/posiciones/`;
    return position
      ? this.api.put<Position>(path + position + '/', body)
      : this.api.post<Position>(path, body);
  }
  closePosition(id: number, position: number, version: number, fecha_salida: string) {
    return this.api.delete<Position>(`/portafolios/${id}/posiciones/${position}/`, {
      version,
      fecha_salida,
    });
  }
  pdf(id: number) {
    return this.api.download(`/portafolios/${id}/export/pdf/`);
  }
  nameValidator(exclude?: number): AsyncValidatorFn {
    return (control) =>
      timer(350).pipe(
        switchMap(() =>
          this.api.get<{ disponible: boolean }>(
            '/portafolios/validar-nombre/',
            { nombre: String(control.value).trim(), excluir: exclude },
            true,
          ),
        ),
        map((result) => (result.disponible ? null : { duplicate: true })),
        catchError(() => of({ availability: true })),
      );
  }
}
