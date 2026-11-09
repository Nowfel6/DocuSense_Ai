const integers = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const utcDateTime = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function formatInteger(value: number): string {
  return integers.format(value);
}

export function formatRate(value: string | null): string {
  if (value === null) return "No data";
  return `${Number(value).toFixed(2)}%`;
}

export function formatDuration(value: number | null): string {
  if (value === null) return "No data";
  if (value < 1_000) return `${formatInteger(value)} ms`;
  if (value < 60_000) return `${(value / 1_000).toFixed(value < 10_000 ? 1 : 0)} s`;
  if (value < 3_600_000) return `${(value / 60_000).toFixed(value < 600_000 ? 1 : 0)} min`;
  return `${(value / 3_600_000).toFixed(1)} h`;
}

export function formatUtc(value: string): string {
  return `${utcDateTime.format(new Date(value))} UTC`;
}

export function formatBucket(value: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}

export function statusLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

