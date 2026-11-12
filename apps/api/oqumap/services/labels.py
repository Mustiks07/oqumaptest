"""Human-readable names for internal codes (topics, objectives, editions) and topic matching by name.

Internal codes (T3, DEMO-M6-3.2, EDA …) stay in the database and in the API for reproducibility; every text a
methodist reads (assistant answers, decision drafts, PDF, sandbox summaries) goes through this module so the same
entity always has the same human name. Kazakh wording is a working draft (not reviewed by a native speaker).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_EDITION_RE = re.compile(r"(пособие|учебник|оқулық|құрал)\s+([A-ZА-ЯЁӘҒҚҢӨҰҮҺІ0-9]{1,3})\b", re.I)


def edition_name(title: str | None, code: str | None = None, lang: str = "ru") -> str:
    """Short user-facing edition name: "Демонстрационное пособие А" → "Пособие А" / "А оқу құралы".

    The rule only shortens titles that end in a book word followed by a letter; any other title is shown as is.
    The internal code is used only when there is no title at all.
    """
    t = (title or "").strip()
    m = _EDITION_RE.search(t)
    if m:
        word, letter = m.group(1).lower(), m.group(2).upper()
        if lang == "kz":
            return f"{letter} оқулығы" if word in ("учебник", "оқулық") else f"{letter} оқу құралы"
        return f"{'Учебник' if word == 'учебник' else 'Пособие'} {letter}"
    return t or (code or "")


def pick(obj: dict, base: str, lang: str) -> str:
    return obj.get(f"{base}_{lang}") or obj.get(f"{base}_ru") or obj.get(base) or ""


# ---------------------------------------------------------------------------
# Topic matching by words ("сложение дробей" → T3)
# ---------------------------------------------------------------------------

_STOP = {"и", "в", "на", "по", "с", "к", "для", "за", "счёт", "счет", "тема", "темы", "тему", "темой", "часы", "часа", "час",
         "часов", "тақырып", "тақырыбы", "сағат", "және", "мен", "пен", "бен", "или", "не", "без", "все", "всех", "раздел",
         # request verbs and book words: never part of a topic name in a question
         "сравни", "сравните", "сравнить", "покажи", "покажите", "добавь", "добавить", "сколько", "почему", "пособия",
         "пособие", "пособий", "учебник", "учебники", "учебника", "оқулық", "құрал", "салыстыр", "неше", "қанша"}


def _stems(text: str) -> set[str]:
    words = re.findall(r"[a-zа-яёәғқңөұүһі]+", text.lower())
    return {w[:5] if len(w) > 5 else w for w in words if len(w) >= 4 and w not in _STOP}


@dataclass
class TopicRef:
    code: str
    title_ru: str
    title_kz: str
    extra: dict = field(default_factory=dict)

    def name(self, lang: str = "ru") -> str:
        return self.title_kz if lang == "kz" and self.title_kz else self.title_ru


def match_topics(text: str, topics: list[TopicRef]) -> list[TopicRef]:
    """Topics whose title shares the most word stems with ``text`` (ties are all returned; codes also match).

    Deterministic and transparent: the methodist sees which topics were recognised before anything is computed.
    """
    low = text.lower()
    by_code = [t for t in topics if re.search(rf"(?<![\w]){re.escape(t.code.lower())}(?![\w.])", low)]
    if by_code:
        return by_code
    stems = _stems(text)
    if not stems:
        return []
    scored = []
    for t in topics:
        title = _stems(t.title_ru) | _stems(t.title_kz)
        hit = len(stems & title)
        # a 4-letter prefix still counts ("дроби" vs "дробей"), but weaker than a 5-letter stem
        weak = len({s[:4] for s in stems} & {s[:4] for s in title}) - hit
        score = hit + 0.5 * max(0, weak)
        if score > 0:
            scored.append((score, t))
    if not scored:
        return []
    best = max(s for s, _ in scored)
    return [t for s, t in scored if s == best]


# ---------------------------------------------------------------------------
# Replace internal codes in free text (live model answers) with human names
# ---------------------------------------------------------------------------

FORBIDDEN_TOKENS = ("comparable", "not_comparable", "adjusted_association", "descriptive", "cluster_robust", "target_hours",
                    "confirmed_only", "as_incorrect", "include_proposed", "pooled", "analysis_id", "b_higher", "a_higher",
                    "no_clear_difference", "undetermined")


@dataclass
class Humanizer:
    topics: dict[str, tuple[str, str]] = field(default_factory=dict)       # code -> (ru, kz)
    objectives: dict[str, tuple[str, str]] = field(default_factory=dict)   # code -> (ru, kz)
    editions: dict[str, tuple[str, str]] = field(default_factory=dict)     # code -> (ru, kz)
    items: dict[str, str] = field(default_factory=dict)                    # code -> stem

    @classmethod
    def from_meta(cls, meta) -> Humanizer:
        h = cls()
        for t in meta.topics:
            h.topics[t.code] = (t.title_ru, t.title_kz)
        for o in meta.objectives:
            h.objectives[o.code] = (o.text_ru, o.text_kz)
        for e in meta.editions.values():
            h.editions[e.code] = (edition_name(e.title, e.code, "ru"), edition_name(e.title, e.code, "kz"))
        return h

    def topic(self, code: str | None, lang: str = "ru") -> str:
        if code is None:
            return ""
        ru, kz = self.topics.get(code, (code, code))
        return kz if lang == "kz" else ru

    def objective(self, code: str | None, lang: str = "ru") -> str:
        if code is None:
            return ""
        ru, kz = self.objectives.get(code, (code, code))
        return kz if lang == "kz" else ru

    def edition(self, code: str | None, lang: str = "ru") -> str:
        if code is None:
            return ""
        ru, kz = self.editions.get(code, (code, code))
        return kz if lang == "kz" else ru

    def text(self, s: str, lang: str = "ru") -> str:
        """Replace codes with names. Longer codes first so "T1" never eats "T10"; objectives before topics."""
        out = s
        for code in sorted(self.objectives, key=len, reverse=True):
            out = re.sub(rf"(?<![\w-]){re.escape(code)}(?![\w.-])", f"«{self.objective(code, lang)}»", out)
        for code in sorted(self.editions, key=len, reverse=True):
            out = re.sub(rf"(?<![\w-]){re.escape(code)}(?![\w-])", self.edition(code, lang), out)
        for code in sorted(self.topics, key=len, reverse=True):
            out = re.sub(rf"(?:\b[Тт]ем[аеуы]\s+)?(?<![\w-]){re.escape(code)}(?![\w.-])", f"«{self.topic(code, lang)}»", out)
        out = re.sub(r"««([^»]*)»»", r"«\1»", out)
        return out


def leftover_internal(text: str) -> list[str]:
    """Internal tokens that must not reach a methodist (checked after humanising)."""
    low = text.lower()
    found = [tok for tok in FORBIDDEN_TOKENS if re.search(rf"\b{re.escape(tok)}\b", low)]
    found += re.findall(r"\b(?:DEMO-M\d+-[\d.]+|ED[AB]|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b", text)
    return found
