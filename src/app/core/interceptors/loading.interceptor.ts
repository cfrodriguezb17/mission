import { inject } from '@angular/core';
import { HttpInterceptorFn } from '@angular/common/http';
import { finalize } from 'rxjs';
import { LoadingService } from '../services/loading.service';
import { SILENT } from '../services/api.service';
export const loadingInterceptor: HttpInterceptorFn = (request, next) => {
  const loading = inject(LoadingService);
  if (request.context.get(SILENT)) return next(request);
  loading.start();
  return next(request).pipe(finalize(() => loading.stop()));
};
