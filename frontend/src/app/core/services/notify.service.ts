import { Service, inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
@Service()
export class NotifyService {
  private readonly snack = inject(MatSnackBar);
  show(message: string) {
    this.snack.open(message, 'Cerrar', {
      duration: 7000,
      horizontalPosition: 'right',
      verticalPosition: 'bottom',
    });
  }
}
