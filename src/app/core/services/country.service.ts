import { Service, inject } from '@angular/core';
import { ApiService } from './api.service';
import { Country, Exchange, Indicator, Params, Page } from '../models/api.models';
@Service()
export class CountryService {
  private readonly api = inject(ApiService);
  list(params: Params = {}) {
    return this.api.get<Page<Country>>('/paises/', params);
  }
  all() {
    return this.api.all<Country>('/paises/');
  }
  detail(code: string) {
    return this.api.get<Country>(`/paises/${code}/`);
  }
  indicators(code: string, params: Params = {}) {
    return this.api.all<Indicator>(`/paises/${code}/indicadores/`, params);
  }
  exchange(code: string, params: Params = {}) {
    return this.api.all<Exchange>(`/paises/${code}/tipo-cambio/`, params);
  }
}
