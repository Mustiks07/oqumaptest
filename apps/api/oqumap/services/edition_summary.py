"""Edition comparison across the whole programme ("Тема × сравнение пособий") with a verdict in words.

Every row is the same standardised comparison as the single-topic screen (``std-v1``: direct standardisation by
entry level, cluster bootstrap with a fixed seed), so a number in the matrix equals the number on the topic page.
The verdict is computed from the rows — nothing is written in advance:

* ``topic_dependent`` — each edition is ahead somewhere (the 95% interval excludes 0): there is no single best book;
* ``a_ahead`` / ``b_ahead`` — confirmed differences point one way only, in the listed topics;
* ``no_confirmed_difference`` — no topic has an interval that excludes 0;
* ``insufficient`` — no topic could be compared.

The raw (unadjusted) direction is reported next to it so the methodist sees when a plain ranking would mislead.
The table is exploratory (several comparisons at once); this is said on the screen and in the verdict detail.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..errors import ApiError, not_found
from . import analysis as an
from .labels import edition_name
from .messages import COMPARABILITY

METHOD_VERSION_SUMMARY = "edition-summary-v1"


def _pp(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{100 * abs(x):.1f}".replace(".", ",") + " п.п."


def _pp_kz(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{100 * abs(x):.1f}".replace(".", ",") + " п.т."


def _lc_first(s: str) -> str:
    """"Пособие А" → "пособие А" (only the first letter; the edition letter stays upper-case)."""
    return s[:1].lower() + s[1:] if s.startswith(("Пособие", "Учебник")) else s


def _quote_list(names: list[str]) -> str:
    return ", ".join(f"«{n}»" for n in names)


def summary(session: Session, org_id: str, req: an.ComparisonRequest, user_id: str | None = None) -> dict:
    """``req.topic_id`` is ignored (every topic of the programme is compared)."""
    req.filters.validate_values()
    if req.strata_scheme not in an.STRATA_SCHEMES:
        raise ApiError("invalid_parameter", "Неизвестная схема страт", 422, {"allowed": list(an.STRATA_SCHEMES)})
    if req.weight_mode not in an.WEIGHT_MODES:
        raise ApiError("invalid_parameter", "Неизвестный режим весов", 422, {"allowed": list(an.WEIGHT_MODES)})
    if req.edition_a_id == req.edition_b_id:
        raise ApiError("invalid_parameter", "Выберите два разных издания", 422)
    meta = an.load_meta(session, org_id, req.dataset_id)
    for e in (req.edition_a_id, req.edition_b_id):
        if e not in meta.editions:
            raise not_found("edition", e)
    f = req.filters.model_copy(update={"edition_ids": []})
    ed_a, ed_b = meta.editions[req.edition_a_id], meta.editions[req.edition_b_id]

    def compute() -> dict:
        rows = []
        for t in meta.topics:
            r = an._compare_topic(session, meta, t, req, f)
            ci = r["uncertainty"]["adjusted_difference_ci"]
            signal = r["signal"]
            favoured = "b" if signal == "b_higher" else "a" if signal == "a_higher" else None
            raw = r["raw"]
            rows.append({
                "topic_id": t.id, "code": t.code, "title_ru": t.title_ru, "title_kz": t.title_kz,
                "status": r["status"], "status_label_ru": COMPARABILITY[r["status"]][0],
                "status_label_kz": COMPARABILITY[r["status"]][1],
                "raw_a": raw["a"]["mean"], "raw_b": raw["b"]["mean"], "raw_difference": raw["difference"],
                "adjusted_a": r["adjusted"]["a"], "adjusted_b": r["adjusted"]["b"],
                "adjusted_difference": r["adjusted"]["difference"], "ci": ci,
                "ci_unavailable_reason": r["uncertainty"]["unavailable_reason"],
                "signal": signal, "favoured": favoured, "confirmed": favoured is not None,
                "n": {"a": {"learners": raw["a"]["n_learners"], "classes": raw["a"]["n_classes"], "schools": raw["a"]["n_schools"]},
                      "b": {"learners": raw["b"]["n_learners"], "classes": raw["b"]["n_classes"], "schools": raw["b"]["n_schools"]}},
                "reasons": [x for x in r["reasons"] if x["severity"] in ("warn", "fail")],
            })
        return {
            "method_version": METHOD_VERSION_SUMMARY,
            "comparison_method_version": an.METHOD_VERSION,
            "editions": {
                "a": {"id": ed_a.id, "code": ed_a.code, "title": ed_a.title,
                      "name_ru": edition_name(ed_a.title, ed_a.code, "ru"), "name_kz": edition_name(ed_a.title, ed_a.code, "kz")},
                "b": {"id": ed_b.id, "code": ed_b.code, "title": ed_b.title,
                      "name_ru": edition_name(ed_b.title, ed_b.code, "ru"), "name_kz": edition_name(ed_b.title, ed_b.code, "kz")},
            },
            "rows": rows,
            "verdict": verdict(rows, ed_a, ed_b),
            "exploratory": True,
            "strata_scheme": req.strata_scheme, "weight_mode": req.weight_mode,
        }

    params = req.model_dump(exclude={"filters", "dataset_id", "topic_id", "include_topic_table"})
    return an.persist_or_reuse(session, org_id, meta.dataset, "edition_summary", f.model_dump(), params,
                               METHOD_VERSION_SUMMARY, compute, user_id)


def verdict(rows: list[dict], ed_a, ed_b) -> dict:
    na_ru, nb_ru = edition_name(ed_a.title, ed_a.code, "ru"), edition_name(ed_b.title, ed_b.code, "ru")
    na_kz, nb_kz = edition_name(ed_a.title, ed_a.code, "kz"), edition_name(ed_b.title, ed_b.code, "kz")
    compared = [r for r in rows if r["status"] != "not_comparable" and r["adjusted_difference"] is not None]
    a_rows = [r for r in compared if r["favoured"] == "a"]
    b_rows = [r for r in compared if r["favoured"] == "b"]
    unclear = [r for r in compared if r["favoured"] is None]
    not_cmp = [r for r in rows if r not in compared]
    raw_a = [r for r in compared if (r["raw_difference"] or 0) < 0]
    raw_b = [r for r in compared if (r["raw_difference"] or 0) > 0]
    # a plain ranking misleads when the unadjusted leader differs from the adjusted conclusion in some topic
    raw_misleading = any((r["favoured"] == "b" and (r["raw_difference"] or 0) < 0)
                         or (r["favoured"] == "a" and (r["raw_difference"] or 0) > 0) for r in compared) \
        or (bool(a_rows) and bool(b_rows) and (len(raw_a) == len(compared) or len(raw_b) == len(compared)))

    def side(rs: list[dict], lang: str) -> str:
        parts = []
        for r in rs:
            title = r["title_kz"] if lang == "kz" else r["title_ru"]
            parts.append(f"«{title}» ({(_pp_kz if lang == 'kz' else _pp)(r['adjusted_difference'])})")
        return ", ".join(parts)

    def topics_word(n: int, lang: str) -> str:
        if lang == "kz":
            return "тақырыпта" if n == 1 else "тақырыптарда"
        return "теме" if n == 1 else "темах"

    if not compared:
        kind = "insufficient"
        text_ru = "Сравнить пособия нельзя ни по одной теме: группы несопоставимы или не хватает данных."
        text_kz = "Құралдарды бірде-бір тақырып бойынша салыстыру мүмкін емес: топтар салыстырылмайды немесе деректер жеткіліксіз."
    elif a_rows and b_rows:
        kind = "topic_dependent"
        text_ru = (f"Единого лучшего пособия нет. {nb_ru} сильнее в {topics_word(len(b_rows), 'ru')} {side(b_rows, 'ru')}, "
                   f"{_lc_first(na_ru)} — в {topics_word(len(a_rows), 'ru')} "
                   f"{side(a_rows, 'ru')}. Выбирать материал следует по теме, а не единым рейтингом.")
        text_kz = (f"Барлық бағдарлама бойынша бірыңғай үздік құрал жоқ. {nb_kz} {side(b_rows, 'kz')} {topics_word(len(b_rows), 'kz')} күштірек, "
                   f"{na_kz} — {side(a_rows, 'kz')} {topics_word(len(a_rows), 'kz')}. Материалды бірыңғай рейтинг бойынша емес, тақырып бойынша таңдау керек.")
    elif a_rows or b_rows:
        win_rows, nm_ru, nm_kz = (a_rows, na_ru, na_kz) if a_rows else (b_rows, nb_ru, nb_kz)
        kind = "a_ahead" if a_rows else "b_ahead"
        text_ru = (f"{nm_ru} сильнее в {topics_word(len(win_rows), 'ru')} {side(win_rows, 'ru')}; в остальных темах различие "
                   "данными не подтверждается. Это преимущество по отдельным темам, а не рейтинг по всей программе.")
        text_kz = (f"{nm_kz} {side(win_rows, 'kz')} {topics_word(len(win_rows), 'kz')} күштірек; қалған тақырыптарда айырма деректермен "
                   "расталмайды. Бұл жекелеген тақырыптардағы артықшылық, бүкіл бағдарлама рейтингі емес.")
    else:
        kind = "no_confirmed_difference"
        text_ru = ("Ни в одной теме различие между пособиями данными не подтверждается (95% интервал включает 0). "
                   "Это не доказывает равенство пособий: данных недостаточно, чтобы их различить.")
        text_kz = ("Бірде-бір тақырыпта құралдар арасындағы айырма деректермен расталмайды (95% интервал 0-ді қамтиды). "
                   "Бұл құралдардың теңдігін дәлелдемейді: оларды ажыратуға деректер жеткіліксіз.")

    detail_ru, detail_kz = [], []
    if unclear and kind != "no_confirmed_difference":
        names_ru = _quote_list([r["title_ru"] for r in unclear])
        names_kz = _quote_list([r["title_kz"] for r in unclear])
        lean_a = sum(1 for r in unclear if r["adjusted_difference"] < 0)
        lean_b = len(unclear) - lean_a
        lean_ru = (f"; оценки чаще в пользу {'пособия А' if lean_a > lean_b else 'пособия Б'}"
                   if lean_a != lean_b and na_ru.startswith("Пособие") and nb_ru.startswith("Пособие") else "")
        detail_ru.append(f"В темах {names_ru} различие не подтверждается: 95% интервал включает 0{lean_ru}.")
        detail_kz.append(f"{names_kz} тақырыптарында айырма расталмайды: 95% интервал 0-ді қамтиды.")
    if not_cmp:
        detail_ru.append(f"Не сравнивались: {_quote_list([r['title_ru'] for r in not_cmp])} — группы несопоставимы или тема не измерена.")
        detail_kz.append(f"Салыстырылмады: {_quote_list([r['title_kz'] for r in not_cmp])} — топтар салыстырылмайды немесе тақырып өлшенбеген.")
    detail_ru.append("Таблица разведочная: при сравнении многих тем часть различий может оказаться случайной.")
    detail_kz.append("Кесте барлау сипатында: көп тақырыпты салыстырғанда кейбір айырмалар кездейсоқ болуы мүмкін.")

    raw_story_ru = raw_story_kz = None
    if raw_misleading and compared:
        leader_rows, leader_ru, leader_kz = (raw_a, na_ru, na_kz) if len(raw_a) >= len(raw_b) else (raw_b, nb_ru, nb_kz)
        if len(leader_rows) == len(compared):
            raw_story_ru = (f"Без поправки на входной уровень {_lc_first(leader_ru)} "
                            f"впереди во всех {len(compared)} сравнимых темах. Но классы с этим пособием изначально сильнее, "
                            "поэтому такой рейтинг вводит в заблуждение.")
            raw_story_kz = (f"Кіріс деңгейіне түзетусіз {leader_kz} барлық {len(compared)} салыстырылатын тақырыпта алда. Бірақ бұл құралмен "
                            "оқитын сыныптар бастапқыда күштірек, сондықтан мұндай рейтинг адастырады.")
        else:
            raw_story_ru = ("Без поправки на входной уровень направление различий в части тем обратное: группы пособий изначально "
                            "различаются по подготовке, поэтому сырой рейтинг вводит в заблуждение.")
            raw_story_kz = ("Кіріс деңгейіне түзетусіз кейбір тақырыптарда айырма бағыты керісінше: құралдар топтары бастапқы "
                            "дайындығы бойынша ерекшеленеді, сондықтан шикі рейтинг адастырады.")
    return {
        "kind": kind,
        "a_topics": [r["code"] for r in a_rows], "b_topics": [r["code"] for r in b_rows],
        "unclear_topics": [r["code"] for r in unclear], "not_compared_topics": [r["code"] for r in not_cmp],
        "raw_a_ahead_topics": [r["code"] for r in raw_a], "raw_b_ahead_topics": [r["code"] for r in raw_b],
        "raw_misleading": raw_misleading,
        "text_ru": text_ru, "text_kz": text_kz,
        "detail_ru": " ".join(detail_ru), "detail_kz": " ".join(detail_kz),
        "raw_story_ru": raw_story_ru, "raw_story_kz": raw_story_kz,
    }


def default_editions(meta) -> tuple[str | None, str | None]:
    """The two editions actually used by classes in the dataset (stable order by code)."""
    used = sorted({v for v in meta.cohort_edition.values() if v in meta.editions}, key=lambda e: meta.editions[e].code)
    if len(used) < 2:
        return None, None
    return used[0], used[1]


def for_dataset(session: Session, org_id: str, dataset_id: str, filters: an.Filters | None = None,
                user_id: str | None = None) -> dict | None:
    meta = an.load_meta(session, org_id, dataset_id)
    a, b = default_editions(meta)
    if a is None or not meta.topics:
        return None
    req = an.ComparisonRequest(dataset_id=dataset_id, topic_id=meta.topics[0].id, edition_a_id=a, edition_b_id=b,
                               filters=filters or an.Filters())
    return summary(session, org_id, req, user_id)


def row_for(result: dict, topic_code: str) -> dict | None:
    return next((r for r in result["rows"] if r["code"] == topic_code), None)
