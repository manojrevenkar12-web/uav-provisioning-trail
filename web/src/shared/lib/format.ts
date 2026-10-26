/** Formatting in one place, so a number reads the same on every screen. */

const LOCALE = "en-GB";
const ZONE = "Europe/Berlin";

export const num = (x: unknown): number => (x == null || x === "" ? NaN : Number(x));

export function pct(x: unknown, digits = 1): string {
  const n = num(x);
  return Number.isNaN(n)
    ? "n/a"
    : `${(n * 100).toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`;
}

export const int = (x: unknown) => {
  const n = num(x);
  return Number.isNaN(n) ? "n/a" : Math.round(n).toLocaleString(LOCALE);
};

export function date(iso: string | null | undefined): string {
  if (!iso) return "not yet";
  const d = new Date(`${iso.slice(0, 10)}T12:00:00Z`);
  return d.toLocaleDateString(LOCALE, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function time(iso: string | null | undefined): string {
  if (!iso) return "not yet";
  return new Date(iso).toLocaleString(LOCALE, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: ZONE,
  });
}

export const humanise = (s: string) => {
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
};

export function minutes(x: unknown): string {
  const n = num(x);
  if (Number.isNaN(n)) return "n/a";
  if (n < 60) return `${n.toLocaleString(LOCALE, { maximumFractionDigits: 0 })} min`;
  return `${Math.floor(n / 60)} h ${Math.round(n % 60)} min`;
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "not yet";
  return new Date(iso).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit", timeZone: ZONE });
}

/** A unit serial without its common prefix: HX2-26-000154 reads as 000154 on a crowded board. */
export const serialTail = (s: string | null | undefined) => (s ? (s.split("-").at(-1) ?? s) : "");

export const short = (hash: string | null | undefined, n = 10) => (hash ? `${hash.slice(0, n)}…` : "");
