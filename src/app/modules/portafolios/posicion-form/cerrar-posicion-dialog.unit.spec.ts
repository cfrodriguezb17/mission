import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA } from '@angular/material/dialog';
import { ClosePositionDialog } from './cerrar-posicion-dialog.component';
import { position } from '../../../testing/fixtures';

describe('Fecha de cierre de una posición', () => {
  function setup() {
    TestBed.configureTestingModule({
      providers: [{ provide: MAT_DIALOG_DATA, useValue: position() }],
    });
    return TestBed.runInInjectionContext(() => new ClosePositionDialog());
  }
  it.each(['2025-02-29', '2025-04-31'])('RGR cierre: rechaza la fecha imposible %s', (value) => {
    const dialog = setup();
    dialog.date.setValue(value);
    expect(dialog.date.invalid).toBe(true);
  });
  it.each(['2019-12-31', '2020-01-01'])(
    'rechaza salida igual o anterior a entrada: %s',
    (value) => {
      const dialog = setup();
      dialog.date.setValue(value);
      expect(dialog.date.invalid).toBe(true);
    },
  );
  it('acepta una fecha real estrictamente posterior', () => {
    const dialog = setup();
    dialog.date.setValue('2020-01-02');
    expect(dialog.date.valid).toBe(true);
  });
});
