import { Service, inject } from '@angular/core';
import { ApiService } from './api.service';
import { Page, Risk, Params } from '../models/api.models';
@Service()
export class RiesgoService {
  private readonly api = inject(ApiService);
  ranking(silent = false) {
    return this.api.all<Risk>('/riesgo/', { ordering: '-indice_compuesto' }, silent);
  }
  detail(code: string) {
    return this.api.get<{ ultimo: Risk | null; historico: Page<Risk> }>(`/riesgo/${code}/`);
  }
  history(code: string, params: Params = {}) {
    return this.api.all<Risk>(`/riesgo/${code}/historico/`, params);
  }
}
