import { writeFileSync } from 'node:fs';

const value = process.env.API_BASE_URL?.trim();
if (!value) {
  throw new Error('Define API_BASE_URL con la URL HTTPS pública del backend y el sufijo /api.');
}
const url = new URL(value);
const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
if (
  (url.protocol !== 'https:' && !(local && url.protocol === 'http:')) ||
  url.username || url.password || url.search || url.hash ||
  !url.pathname.replace(/\/$/, '').endsWith('/api')
) {
  throw new Error('API_BASE_URL debe ser una URL HTTPS sin credenciales, query ni fragmento y terminar en /api.');
}
const apiBaseUrl = url.href.replace(/\/$/, '');
writeFileSync(
  new URL('../src/environments/environment.production.ts', import.meta.url),
  `export const environment = ${JSON.stringify({ production: true, apiBaseUrl })};\n`,
);
