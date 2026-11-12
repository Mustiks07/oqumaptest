/** Display formatting. Values arrive as shares 0..1; percent only at display time. null → "—". */
import type { Lang } from "../i18n/dict";

const nf = (_lang: Lang, digits: number) =>
  // ru-RU grouping and decimal comma for both languages: kk-KZ is not consistent across browsers (47.1% vs 47,1%)
  new Intl.NumberFormat("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function pct(x: number | null | undefined, lang: Lang = "ru", digits = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "—";
  return `${nf(lang, digits).format(100 * x)}%`;
}

/** Difference of shares in percentage points, always signed and labelled. */
export function pp(x: number | null | undefined, lang: Lang = "ru", digits = 1): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "—";
  const v = 100 * x;
  const s = nf(lang, digits).format(Math.abs(v));
  const sign = v > 0 ? "+" : v < 0 ? "−" : "±";
  return `${sign}${s} ${lang === "kz" ? "п.т." : "п.п."}`;
}

export function num(x: number | null | undefined, lang: Lang = "ru", digits = 0): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return "—";
  return nf(lang, digits).format(x);
}

export function dateTime(iso: string | null | undefined, lang: Lang = "ru"): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return new Intl.DateTimeFormat(lang === "kz" ? "kk-KZ" : "ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(d);
}
