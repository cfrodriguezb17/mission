import { Pipe, PipeTransform } from '@angular/core';
import { label } from '../../core/models/api.models';
@Pipe({ name: 'catalogo' })
export class CatalogoPipe implements PipeTransform {
  transform(value: string): string {
    return label(value);
  }
}
