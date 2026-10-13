import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { PositionDialog, PositionDialogData } from './position-dialog';
import { PortfolioService } from '../../core/services/portfolio.service';
import { PortfolioDetail, Country, Position } from '../../core/models/api.models';
const position = (id: number, amount = '1000.00'): Position => ({
  id,
  pais: 'CO',
  nombre_pais: 'Colombia',
  tipo_activo: 'RENTA_FIJA',
  monto_inversion_usd: amount,
  fecha_entrada: '2020-01-01',
  fecha_salida: null,
  notas: '',
});
describe('Formulario de posiciones', () => {
  function setup(positions: Position[] = [], editing?: Position) {
    const data: PositionDialogData = {
      portfolio: { id: 1, puede_editar: true, posiciones: positions } as PortfolioDetail,
      countries: [
        { codigo_iso: 'CO', nombre: 'Colombia', moneda_codigo: 'COP' },
        { codigo_iso: 'EC', nombre: 'Ecuador', moneda_codigo: 'USD' },
      ] as Country[],
      position: editing,
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: MAT_DIALOG_DATA, useValue: data },
        { provide: MatDialogRef, useValue: { close: vi.fn() } },
        { provide: PortfolioService, useValue: { savePosition: vi.fn() } },
      ],
    });
    return TestBed.runInInjectionContext(() => new PositionDialog());
  }
  it('prohíbe MONEDA en economías con USD', () => {
    const component = setup();
    component.form.patchValue({ pais: 'EC', tipo_activo: 'MONEDA', monto_inversion_usd: '1000' });
    expect(component.form.getError('cross')).toContain('USD');
  });
  it('bloquea la tercera posición activa del mismo país y tipo', () => {
    const component = setup([position(1), position(2)]);
    component.form.patchValue({
      pais: 'CO',
      tipo_activo: 'RENTA_FIJA',
      monto_inversion_usd: '1000',
    });
    expect(component.form.getError('cross')).toContain('dos posiciones');
  });
  it('excluye la posición editada de los límites', () => {
    const first = position(1);
    const component = setup([first, position(2)], first);
    expect(component.form.valid).toBe(true);
  });
  it('suma el capital en centavos y bloquea el exceso de 50 millones', () => {
    const positions = Array.from({ length: 5 }, (_, i) => ({
      ...position(i, '10000000.00'),
      tipo_activo: 'COMMODITIES',
    }));
    const component = setup(positions);
    component.form.patchValue({
      pais: 'CO',
      tipo_activo: 'RENTA_FIJA',
      monto_inversion_usd: '1000.01',
    });
    expect(component.form.getError('cross')).toContain('50,000,000');
  });
  it('rechaza un texto de país que no proviene del catálogo', () => {
    const component = setup();
    component.form.controls.pais.setValue('Colombia cualquiera');
    expect(component.form.controls.pais.hasError('country')).toBe(true);
  });
  it('no hace solicitudes con datos inválidos', () => {
    const component = setup();
    component.save();
    expect(TestBed.inject(PortfolioService).savePosition).not.toHaveBeenCalled();
  });
  it('ignora las posiciones cerradas en el cupo por país y en el capital activo', () => {
    const component = setup([
      { ...position(1, '10000000.00'), fecha_salida: '2020-02-01' },
      { ...position(2, '10000000.00'), fecha_salida: '2020-02-01' },
    ]);
    component.form.patchValue({
      pais: 'CO',
      tipo_activo: 'RENTA_FIJA',
      monto_inversion_usd: '1000.00',
    });
    expect(component.form.valid).toBe(true);
  });
  it('permite exactamente 50 millones y rechaza un centavo adicional', () => {
    const positions = Array.from({ length: 4 }, (_, id) => ({
      ...position(id, '10000000.00'),
      tipo_activo: 'COMMODITIES',
    }));
    positions.push({ ...position(5, '9998999.99'), tipo_activo: 'COMMODITIES' });
    const component = setup(positions);
    component.form.patchValue({
      pais: 'CO',
      tipo_activo: 'RENTA_FIJA',
      monto_inversion_usd: '1000.01',
    });
    expect(component.form.valid).toBe(true);
    component.form.controls.monto_inversion_usd.setValue('1000.02');
    expect(component.form.getError('cross')).toContain('50,000,000');
  });
});
