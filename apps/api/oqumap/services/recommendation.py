"""Facts behind a methodist recommendation, shared by the decision draft, the assistant and the PDF.

Everything here is computed from stored analyses — the topic analysis, the hour plan (a stored plan scenario or the
balanced scenario of the current plan) and the programme-wide edition comparison:

* ``hours_story`` — how many hours the plan adds to the topic, where they come from and why;
* ``material_choice`` — which fragment to teach from, preferring the edition that is stronger *in this topic*; when
  the stronger edition has no fragment for the weak objective, the other edition is used and the reason is stated.

The texts are deterministic (RU/KZ); a model may rephrase them but cannot change the numbers (see ``ai.verify``).
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..errors import ApiError
from . import analysis as an
from . import planning
from .labels import edition_name


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f}".replace(".", ",") + "%"


def _pp(x: float | None, lang: str = "ru") -> str:
    if x is None:
        return "—"
    return f"{100 * abs(x):.1f}".replace(".", ",") + (" п.т." if lang == "kz" else " п.п.")


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """Russian plural: (1 ученик, 2 ученика, 5 учеников)."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return forms[1]
    return forms[2]


def snippet(text: str, limit: int = 70) -> str:
    """First words of a fragment, cut at a word boundary ("Модель. Чтобы вычислить 3 1/4 − 1 3/4, двигаемся…")."""
    t = " ".join(text.split())
    if len(t) <= limit:
        return t.rstrip(".")
    cut = t[:limit].rsplit(" ", 1)[0].rstrip(",.;:")
    return cut + "…"


def hours_word(n: int, lang: str = "ru") -> str:
    if lang == "kz":
        return "сағат"
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return "час"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "часа"
    return "часов"


# ---------------------------------------------------------------------------
# Plan scenario
# ---------------------------------------------------------------------------


def default_solve_request(ctx: dict, dataset_id: str, filters: an.Filters, presets: list[str]) -> planning.PlanSolveRequest:
    return planning.PlanSolveRequest(
        dataset_id=dataset_id, filters=filters, budget=ctx["budget"], presets=presets,
        source_analysis_id=ctx["source_analysis_id"], plan_id=(ctx.get("plan") or {}).get("id"),
        topics=[planning.TopicInput(topic_id=t["topic_id"], code=t["code"], title=t["title_ru"], current_hours=t["current_hours"],
                                    priority=t["priority"], min_hours=t["min_hours"], max_hours=t["max_hours"],
                                    elapsed_hours=t["elapsed_hours"]) for t in ctx["topics"]])


def plan_scenario(session: Session, org_id: str, dataset_id: str, filters: an.Filters, user_id: str | None,
                  plan_analysis_id: str | None = None, preset: str | None = None) -> dict | None:
    """A stored plan scenario (when given) or the balanced scenario of the current plan, computed and stored now."""
    if plan_analysis_id:
        run = an.get_run(session, org_id, plan_analysis_id)
        res, ctx = run["result"], run["context"]
    else:
        pctx = planning.plan_context(session, org_id, dataset_id, filters, user_id)
        if not pctx["topics"]:
            return None
        out = planning.solve(session, org_id, default_solve_request(pctx, dataset_id, filters, ["balanced"]), user_id)
        res, ctx = out["result"], out["context"]
    scen = next((s for s in res["scenarios"] if s["preset"] == preset), None) if preset else None
    scen = scen or next((s for s in res["scenarios"] if s["status"] in ("optimal", "feasible")), None)
    if scen is None:
        return None
    return {"analysis_id": ctx["analysis_id"], "preset": scen["preset"], "scenario": scen, "is_stale": ctx["is_stale"]}


def hours_story(scen: dict | None, topic_code: str, names: dict[str, tuple[str, str]]) -> dict | None:
    """Hours for ``topic_code`` in a plan scenario, the donors and the reasons, with RU/KZ sentences."""
    if scen is None or scen["scenario"]["status"] not in ("optimal", "feasible"):
        return None
    changes = scen["scenario"]["changes"]
    row = next((c for c in changes if c["code"] == topic_code), None)
    if row is None:
        return None
    donors = [c for c in changes if c["delta"] < 0]
    others = [c for c in changes if c["delta"] > 0 and c["code"] != topic_code]

    def nm(code: str, lang: str) -> str:
        ru, kz = names.get(code, (code, code))
        return kz if lang == "kz" else ru

    d = row["delta"]
    title_ru, title_kz = nm(topic_code, "ru"), nm(topic_code, "kz")
    donors_ru = ", ".join(f"«{nm(c['code'], 'ru')}» (−{-c['delta']} ч)" for c in donors)
    donors_kz = ", ".join(f"«{nm(c['code'], 'kz')}» (−{-c['delta']} сағ)" for c in donors)
    if d > 0:
        action_ru = (f"Добавить {d} {hours_word(d)} на тему «{title_ru}» ({row['before']} → {row['after']} ч)"
                     + (f"; часы перенести из {'темы' if len(donors) == 1 else 'тем'} {donors_ru}" if donors else "") + ".")
        action_kz = (f"«{title_kz}» тақырыбына {d} сағат қосу ({row['before']} → {row['after']} сағ)"
                     + (f"; сағаттар {donors_kz} тақырыбынан ауыстырылады" if donors else "") + ".")
    elif d < 0:
        action_ru = f"Сократить тему «{title_ru}» на {-d} {hours_word(d)} ({row['before']} → {row['after']} ч)."
        action_kz = f"«{title_kz}» тақырыбын {-d} сағатқа қысқарту ({row['before']} → {row['after']} сағ)."
    else:
        action_ru = f"Часы темы «{title_ru}» не меняются ({row['before']} ч): план не находит выигрыша от переноса при текущих ограничениях."
        action_kz = f"«{title_kz}» тақырыбының сағаты өзгермейді ({row['before']} сағ): ағымдағы шектеулерде ауыстырудан пайда жоқ."
    donor_reasons_ru = [f"«{nm(c['code'], 'ru')}»: {c.get('donor_reason_ru') or c['reason_ru']}" for c in donors]
    donor_reasons_kz = [f"«{nm(c['code'], 'kz')}»: {c.get('donor_reason_kz') or c['reason_kz']}" for c in donors]
    return {
        "analysis_id": scen["analysis_id"], "preset": scen["preset"], "is_stale": scen["is_stale"],
        "topic_code": topic_code, "before": row["before"], "after": row["after"], "delta": d,
        "reason_ru": row["reason_ru"], "reason_kz": row["reason_kz"],
        "donors": [{"code": c["code"], "title_ru": nm(c["code"], "ru"), "title_kz": nm(c["code"], "kz"), "before": c["before"],
                    "after": c["after"], "delta": c["delta"], "reason_ru": c.get("donor_reason_ru") or c["reason_ru"],
                    "reason_kz": c.get("donor_reason_kz") or c["reason_kz"]} for c in donors],
        "other_additions": [{"code": c["code"], "title_ru": nm(c["code"], "ru"), "title_kz": nm(c["code"], "kz"),
                             "delta": c["delta"]} for c in others],
        "action_ru": action_ru, "action_kz": action_kz,
        "donor_reasons_ru": donor_reasons_ru, "donor_reasons_kz": donor_reasons_kz,
        "total_before": scen["scenario"].get("total_before"), "total_after": scen["scenario"].get("total_after"),
    }


# ---------------------------------------------------------------------------
# Material choice
# ---------------------------------------------------------------------------

_MATH = re.compile(r"\d+\s+\d+/\d+|\d+/\d+")


def _source_label(s: dict, lang: str) -> str:
    name = edition_name(s.get("edition_title"), s.get("edition_code"), lang)
    page = f", с. {s['page_printed']}" if lang == "ru" and s.get("page_printed") else (
        f", {s['page_printed']}-бет" if s.get("page_printed") else "")
    return f"{name}{page}: «{snippet(s['excerpt'])}»"


def material_choice(tr: dict, summary_row: dict | None, editions: dict | None) -> dict:
    """Fragments for the weakest objective, from the edition that is stronger in this topic when it has one."""
    measured = [o for o in tr["objectives"] if o["score"]]
    weakest = min(measured, key=lambda o: o["score"]["mean"]) if measured else None
    items = [it for it in tr["items"] if weakest and any(ol["code"] == weakest["code"] for ol in it.get("objectives", []))]
    weakest_item = min(items, key=lambda it: (it["p_correct"] is None, it["p_correct"] or 0)) if items else None
    item_math = set(_MATH.findall(weakest_item["stem_ru"])) if weakest_item else set()
    pool = [s for s in tr["sources"] if weakest and s["objective_code"] == weakest["code"]] or list(tr["sources"])

    def score(s: dict) -> tuple:
        return (s["status"] != "confirmed", len(s["excerpt"]) < 60, -len(item_math & set(_MATH.findall(s["excerpt"]))), s["anchor"])

    fav_key = summary_row.get("favoured") if summary_row else None
    fav = (editions or {}).get(fav_key) if fav_key else None
    diff = summary_row.get("adjusted_difference") if summary_row else None
    preferred = sorted([s for s in pool if fav and s["edition_code"] == fav["code"]], key=score)
    if fav and preferred:
        chosen, kind = preferred[:1], "stronger_edition"
        why_ru = (f"{fav['name_ru']} сильнее в этой теме (+{_pp(diff)} после учёта входного уровня), поэтому объяснение "
                  "берём из него.")
        why_kz = (f"{fav['name_kz']} бұл тақырыпта күштірек (кіріс деңгейін ескергенде +{_pp(diff, 'kz')}), сондықтан "
                  "түсіндіруді осы құралдан аламыз.")
    elif fav:
        chosen, kind = sorted(pool, key=score)[:1], "stronger_edition_has_no_fragment"
        why_ru = (f"{fav['name_ru']} сильнее в этой теме, но в нём нет фрагмента для слабой цели; до появления такого "
                  "фрагмента используем доступный материал и отмечаем это в решении.")
        why_kz = (f"{fav['name_kz']} бұл тақырыпта күштірек, бірақ онда әлсіз мақсатқа арналған үзінді жоқ; "
                  "қолжетімді материалды пайдаланамыз.")
    else:
        chosen, kind = sorted(pool, key=score)[:1], "no_confirmed_difference" if summary_row else "no_comparison"
        why_ru = ("Различие пособий в этой теме данными не подтверждается, поэтому фрагмент выбран по слабой цели, "
                  "а не по пособию.") if summary_row else "Сравнение пособий по теме недоступно; фрагмент выбран по слабой цели."
        why_kz = ("Бұл тақырыпта құралдар арасындағы айырма расталмаған, сондықтан үзінді әлсіз мақсат бойынша таңдалды."
                  if summary_row else "Құралдарды салыстыру қолжетімсіз; үзінді әлсіз мақсат бойынша таңдалды.")
    unconfirmed = any(s["status"] != "confirmed" for s in chosen)
    return {
        "kind": kind, "favoured_edition_code": fav["code"] if fav else None,
        "source_ids": [s["source_id"] for s in chosen], "sources": chosen,
        "weakest_objective": None if weakest is None else {"code": weakest["code"], "text_ru": weakest["text_ru"],
                                                            "text_kz": weakest["text_kz"], "score": weakest["score"]["mean"]},
        "weakest_item": None if weakest_item is None else {"code": weakest_item["code"], "stem_ru": weakest_item["stem_ru"],
                                                           "p_correct": weakest_item["p_correct"]},
        "labels_ru": [_source_label(s, "ru") for s in chosen], "labels_kz": [_source_label(s, "kz") for s in chosen],
        "why_ru": why_ru, "why_kz": why_kz, "unconfirmed_link": unconfirmed,
    }


def summary_for(session: Session, org_id: str, dataset_id: str, filters: an.Filters, user_id: str | None) -> dict | None:
    from . import edition_summary as es

    try:
        return es.for_dataset(session, org_id, dataset_id, filters.model_copy(), user_id)
    except ApiError:
        return None
