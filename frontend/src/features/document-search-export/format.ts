const GROUP = /\B(?=(\d{3})+(?!\d))/g;

export function formatMoneyString(value: string | null, currency: string | null): string {
  if (value === null) return "Not available";
  const [integer, fraction] = value.split(".");
  const normalized = `${integer.replace(GROUP, ",")}${fraction === undefined ? "" : `.${fraction}`}`;
  return currency ? `${currency} ${normalized}` : normalized;
}

export function formatSimilarity(value: number | null): string {
  return value === null ? "Not available" : value.toFixed(3);
}

export function exportDownloadPath(exportId: string): string {
  return `/api/backend/api/v1/exports/${encodeURIComponent(exportId)}/download`;
}
