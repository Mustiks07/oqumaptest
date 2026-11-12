"""Coherence of a decision card: the text, the attached plan, the comparison and the materials must agree.

Checks (``critical`` blocks approval; ``warning`` is shown prominently but does not block):

* ``analysis_missing`` (critical) — no topic analysis is attached or it no longer exists;
* ``analysis_stale`` / ``plan_stale`` (critical) — the data changed after the analysis or the plan was computed;
* ``plan_hours_not_in_action`` (critical) — a plan that changes the topic's hours is attached, but the action does
  not state that number of hours;
* ``material_contradicts_comparison`` (critical) — the comparison found one edition stronger in this topic, every
  cited fragment is from the other edition and the action gives no reason for that;
* ``comparison_not_comparable`` (critical) — the attached comparison is between non-comparable groups;
* ``comparison_other_topic`` (warning) — the attached comparison is about another topic;
* ``no_sources`` (warning) — no material fragment is cited;
* ``hours_without_plan`` (warning) — the action promises hours but no plan is attached.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .labels import edition_name

MESSAGES = {
    "analysis_missing": ("Анализ темы не найден: соберите решение заново со страницы темы.",
                         "Тақырып талдауы табылмады: шешімді тақырып бетінен қайта жинаңыз."),
    "analysis_stale": ("Данные изменились после расчёта анализа: пересчитайте анализ перед утверждением.",
                       "Талдау есептелгеннен кейін деректер өзгерді: бекіту алдында талдауды қайта есептеңіз."),
    "plan_stale": ("План часов рассчитан на устаревших данных: пересчитайте план.",
                   "Сағат жоспары ескі деректер бойынша есептелген: жоспарды қайта есептеңіз."),
    "plan_hours_not_in_action": ("Прикреплённый план меняет часы темы на {delta} ч ({before} → {after}), но в действии это число не указано.",
                                 "Тіркелген жоспар тақырып сағатын {delta} сағ өзгертеді ({before} → {after}), бірақ әрекетте бұл сан көрсетілмеген."),
    "material_contradicts_comparison": ("Сравнение показало, что в этой теме сильнее «{favoured}», но все выбранные фрагменты из «{used}», "
                                        "и причина не объяснена.",
                                        "Салыстыру бұл тақырыпта «{favoured}» күштірек екенін көрсетті, бірақ барлық үзінді «{used}» "
                                        "құралынан алынған және себебі түсіндірілмеген."),
    "comparison_not_comparable": ("Прикреплённое сравнение пособий выполнено на несопоставимых группах — на него нельзя опираться.",
                                  "Тіркелген салыстыру салыстыруға келмейтін топтарда жасалған — оған сүйенуге болмайды."),
    "comparison_other_topic": ("Прикреплённое сравнение пособий относится к другой теме.",
                               "Тіркелген салыстыру басқа тақырыпқа қатысты."),
    "no_sources": ("Не выбран ни один фрагмент учебного материала.", "Оқу материалының бірде-бір үзіндісі таңдалмаған."),
    "hours_without_plan": ("В действии указаны часы, но план часов не прикреплён и не проверен.",
                           "Әрекетте сағат көрсетілген, бірақ сағат жоспары тіркелмеген және тексерілмеген."),
}
SEVERITY = {"analysis_missing": "critical", "analysis_stale": "critical", "plan_stale": "critical",
            "plan_hours_not_in_action": "critical", "material_contradicts_comparison": "critical",
            "comparison_not_comparable": "critical", "comparison_other_topic": "warning", "no_sources": "warning",
            "hours_without_plan": "warning"}

_JUSTIFY = re.compile(r"потому что|так как|поскольку|причин|из-за|нет фрагмента|себебі|өйткені|жоқ|себеп", re.I)
_HOURS_PROMISE = re.compile(r"(?:добав\w*|сократ\w*|перенес\w*|қос\w*)\s+\d+\s*(?:ч\b|час|сағ)", re.I)


def issue(code: str, **params) -> dict:
    ru, kz = MESSAGES[code]
    return {"code": code, "severity": SEVERITY[code], "message_ru": ru.format(**params), "message_kz": kz.format(**params),
            "params": params}


def states_hours(action: str, delta: int, before: int | None = None, after: int | None = None) -> bool:
    n = abs(delta)
    pats = [rf"(?<![\d,.]){n}\s*(?:ч\b|ч\.|час|сағ)", rf"[+−-]\s*{n}\s*(?:ч\b|ч\.|час|сағ)"]
    if before is not None and after is not None:
        pats.append(rf"{before}\s*(?:→|->|—|до)\s*{after}")
    return any(re.search(p, action, re.I) for p in pats)


def check_text_coherence(action: str, hs: dict | None, mat: dict | None, sources_by_id: dict[str, dict],
                         citations: list[str]) -> list[str]:
    """Codes of critical inconsistencies in a generated draft (used to reject a model's rewrite)."""
    bad = []
    if hs and hs["delta"] and not states_hours(action, hs["delta"], hs["before"], hs["after"]):
        bad.append("plan_hours_not_in_action")
    fav = (mat or {}).get("favoured_edition_code")
    used = {sources_by_id[c]["edition_code"] for c in citations if c in sources_by_id}
    if fav and used and fav not in used and not _JUSTIFY.search(action):
        bad.append("material_contradicts_comparison")
    return bad


def evaluate(session: Session, org_id: str, ds: m.Dataset, topic_id: str | None, action: str, analysis_ids: list[str],
             plan_analysis_id: str | None, plan_preset: str | None, source_editions: list[str | None]) -> list[dict]:
    """All checks for a draft (before saving) or a saved decision. Never raises for missing analyses: reports them."""
    runs = {r.id: r for r in session.scalars(select(m.AnalysisRun).where(m.AnalysisRun.org_id == org_id,
                                                                         m.AnalysisRun.id.in_(analysis_ids or [""])))}
    issues: list[dict] = []
    topic_runs = [r for r in runs.values() if r.kind == "topic_evidence"]
    if not topic_runs or len(runs) < len([a for a in analysis_ids if a]):
        issues.append(issue("analysis_missing"))
    if any(r.dataset_version != ds.version for r in runs.values()):
        issues.append(issue("analysis_stale"))
    topic = session.get(m.Topic, topic_id) if topic_id else None
    topic_code = topic.code if topic else (topic_runs[0].result["topic"]["code"] if topic_runs else None)

    # plan
    if plan_analysis_id:
        plan_run = session.scalar(select(m.AnalysisRun).where(m.AnalysisRun.org_id == org_id, m.AnalysisRun.id == plan_analysis_id))
        if plan_run is None:
            issues.append(issue("analysis_missing"))
        else:
            if plan_run.dataset_version != ds.version:
                issues.append(issue("plan_stale"))
            scen = next((s for s in plan_run.result.get("scenarios", []) if s["preset"] == plan_preset), None) \
                or next((s for s in plan_run.result.get("scenarios", []) if s["status"] in ("optimal", "feasible")), None)
            row = next((c for c in (scen or {}).get("changes", []) if c["code"] == topic_code), None)
            if row and row["delta"] and not states_hours(action, row["delta"], row["before"], row["after"]):
                issues.append(issue("plan_hours_not_in_action", delta=f"{row['delta']:+d}".replace("-", "−"),
                                    before=row["before"], after=row["after"]))
    elif _HOURS_PROMISE.search(action):
        issues.append(issue("hours_without_plan"))

    # comparison and materials
    favoured: tuple[str, str] | None = None
    for r in runs.values():
        if r.kind != "comparison":
            continue
        res = r.result
        if res["status"] == "not_comparable":
            issues.append(issue("comparison_not_comparable"))
        if topic_code and res["topic"]["code"] != topic_code:
            issues.append(issue("comparison_other_topic"))
            continue
        side = {"b_higher": "b", "a_higher": "a"}.get(res["signal"])
        if side:
            e = res["editions"][side]
            favoured = (e["code"], e.get("name_ru") or edition_name(e.get("title"), e["code"]))
    if favoured is None and topic_code:
        summ = next((r for r in session.scalars(select(m.AnalysisRun).where(
            m.AnalysisRun.org_id == org_id, m.AnalysisRun.dataset_id == ds.id, m.AnalysisRun.kind == "edition_summary",
            m.AnalysisRun.dataset_version == ds.version).order_by(m.AnalysisRun.created_at.desc()))), None)
        if summ is not None:
            row = next((x for x in summ.result["rows"] if x["code"] == topic_code), None)
            if row and row.get("favoured"):
                e = summ.result["editions"][row["favoured"]]
                favoured = (e["code"], e["name_ru"])
    used = {e for e in source_editions if e}
    if not source_editions:
        issues.append(issue("no_sources"))
    elif favoured and used and favoured[0] not in used and not _JUSTIFY.search(action):
        other = next(iter(used))
        e = session.scalar(select(m.TextbookEdition).where(m.TextbookEdition.org_id == org_id, m.TextbookEdition.code == other))
        issues.append(issue("material_contradicts_comparison", favoured=favoured[1],
                            used=edition_name(e.title, e.code) if e else other))
    # one message per code
    seen, out = set(), []
    for x in issues:
        if x["code"] not in seen:
            seen.add(x["code"])
            out.append(x)
    return out


def blocking(issues: list[dict]) -> list[dict]:
    return [x for x in issues if x["severity"] == "critical"]
