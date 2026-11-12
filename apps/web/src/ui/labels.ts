/** One place for user-facing names of internal entities and codes.
 *
 *  Internal codes (T3, DEMO-M6-3.2, EDA, enum values such as `comparable` or `as_incorrect`) stay in the API and in
 *  the database for reproducibility. Screens show the human names below; a code is shown only inside
 *  "Технические сведения". Every component uses these helpers instead of ad-hoc string replacements. */
import { useMemo } from "react";
import { useCurriculum } from "../api/hooks";
import { useI18n } from "../i18n/I18n";
import type { DictKey, Lang } from "../i18n/dict";

export interface EditionLike {
  id?: string;
  code?: string | null;
  title?: string | null;
  name_ru?: string | null;
  name_kz?: string | null;
}

const EDITION_RE = /(пособие|учебник|оқулық|құрал)\s+([A-ZА-ЯЁӘҒҚҢӨҰҮҺІ0-9]{1,3})\b/i;

/** "Демонстрационное пособие А" → "Пособие А" / "А оқу құралы"; the server sends the same names (name_ru/name_kz). */
export function editionName(e: EditionLike | null | undefined, lang: Lang): string {
  if (!e) return "—";
  const fromServer = lang === "kz" ? e.name_kz : e.name_ru;
  if (fromServer) return fromServer;
  const title = (e.title ?? "").trim();
  const m = EDITION_RE.exec(title);
  if (m) {
    const word = m[1].toLowerCase();
    const letter = m[2].toUpperCase();
    if (lang === "kz") return word === "учебник" || word === "оқулық" ? `${letter} оқулығы` : `${letter} оқу құралы`;
    return `${word === "учебник" ? "Учебник" : "Пособие"} ${letter}`;
  }
  return title || e.code || "—";
}

/** Dictionary key for an enum value, when it exists: label("comparability", "comparable"). */
export function enumKey(prefix: string, value: string | null | undefined): DictKey {
  return `${prefix}.${value ?? ""}` as DictKey;
}

export interface Labels {
  topic: (codeOrId: string | null | undefined) => string;
  objective: (code: string | null | undefined) => string;
  edition: (codeOrId: string | null | undefined) => string;
  /** replace any known code inside a server text with its human name */
  text: (s: string | null | undefined) => string;
  ready: boolean;
}

/** Names from the current programme (curriculum endpoint). Falls back to the code only while loading. */
export function useLabels(): Labels {
  const { lang } = useI18n();
  const cur = useCurriculum();
  return useMemo(() => {
    const d = cur.data;
    const topics = new Map<string, string>();
    const objectives = new Map<string, string>();
    const editions = new Map<string, string>();
    for (const t of d?.topics ?? []) {
      const name = (lang === "kz" ? t.title_kz : t.title_ru) || t.title_ru;
      topics.set(t.code, name);
      topics.set(t.id, name);
    }
    for (const o of d?.objectives ?? []) objectives.set(o.code, (lang === "kz" ? o.text_kz : o.text_ru) || o.text_ru);
    for (const e of d?.editions ?? []) {
      const name = editionName(e as EditionLike, lang);
      if (e.code) editions.set(e.code, name);
      editions.set(e.id, name);
    }
    const text = (s: string | null | undefined) => {
      if (!s) return "";
      let out = s;
      const replace = (map: Map<string, string>, quote: boolean) => {
        const codes = Array.from(map.keys()).filter((k) => k.length < 30).sort((a, b) => b.length - a.length);
        for (const code of codes) {
          const esc = code.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          out = out.replace(new RegExp(`(?<![\\w-])${esc}(?![\\w.-])`, "g"), quote ? `«${map.get(code)}»` : map.get(code)!);
        }
      };
      replace(objectives, true);
      replace(editions, false);
      replace(topics, true);
      return out.replace(/««([^»]*)»»/g, "«$1»");
    };
    return {
      topic: (c) => (c ? topics.get(c) ?? c : "—"),
      objective: (c) => (c ? objectives.get(c) ?? c : "—"),
      edition: (c) => (c ? editions.get(c) ?? c : "—"),
      text,
      ready: !!d,
    };
  }, [cur.data, lang]);
}

/** Tokens that must never appear in the primary (non-technical) view. Used by tests and by a dev-only check. */
export const RAW_TOKENS = [
  "DEMO-M6", "cluster_robust_t_class", "target_hours", "adjusted_association", "comparable", "confirmed_only", "as_incorrect",
] as const;
