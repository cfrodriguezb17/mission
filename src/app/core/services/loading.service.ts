import { Service, signal, computed } from '@angular/core';
@Service()
export class LoadingService {
  private readonly count = signal(0);
  readonly active = computed(() => this.count() > 0);
  start() {
    this.count.update((n) => n + 1);
  }
  stop() {
    this.count.update((n) => Math.max(0, n - 1));
  }
}
