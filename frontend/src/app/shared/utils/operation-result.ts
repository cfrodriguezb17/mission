function hasContent(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === 'object') return Object.values(value).some(hasContent);
  return Boolean(value);
}
/** Inspect only error/missing/pending fields; processed-country arrays are successful output. */
export function hasOperationIssues(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  return Object.entries(value).some(([key, item]) =>
    /pendiente|errores|faltantes/.test(key) ? hasContent(item) : hasOperationIssues(item),
  );
}
