"""Hours planning on top of a teaching plan and the current topic analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..analytics import planner as pl
from ..errors import ApiError, not_found
from . import analysis as an
from .messages import PLAN_STATUS, label_constraint

PRESETS = ("balanced", "minimal_changes", "focus_problem_topics")


class TopicInput(BaseModel):
    topic_id: str | None = None
    code: str
    title: str = ""
    current_hours: int
    priority: float = 1.0
    min_hours: int | None = None
    max_hours: int | None = None
    fixed: bool = False
    elapsed_hours: int = 0
    max_change: int | None = None


class PlanSolveRequest(BaseModel):
    dataset_id: str
    plan_id: str | None = None
    filters: an.Filters = Field(default_factory=an.Filters)
    topics: list[TopicInput]
    budget: int
    change_penalty: float = 0.05
    diminishing_rate: float | None = None
    presets: list[str] = Field(default_factory=lambda: ["balanced"])
    time_limit_seconds: float = 5.0
    source_analysis_id: str | None = None


def plan_context(session: Session, org_id: str, dataset_id: str, filters: an.Filters, user_id: str | None) -> dict:
    """Current plan + suggested priorities derived from the topic analysis (editable by the methodist)."""
    ds = an.get_dataset(session, org_id, dataset_id)
    plan = session.scalar(select(m.TeachingPlan).where(m.TeachingPlan.dataset_id == ds.id, m.TeachingPlan.org_id == org_id)
                          .order_by(m.TeachingPlan.created_at.desc(), m.TeachingPlan.version.desc()))
    ov = an.overview(session, org_id, dataset_id, filters, user_id)
    by_topic = {t["topic_id"]: t for t in ov["result"]["topics"]}
    deficits = [t["deficit"] for t in by_topic.values() if t["deficit"] is not None]
    dmax = max(deficits) if deficits else 1.0
    evidence_by_topic: dict[str, dict] = {}
    for topic_id, row in by_topic.items():
        if row.get("status") not in ("difficult", "attention", "stable"):
            continue
        evidence = an.topic_evidence(session, org_id, dataset_id, topic_id, filters, user_id)["result"]
        measured_objectives = [o for o in evidence["objectives"] if (o.get("score") or {}).get("mean") is not None]
        weakest = min(measured_objectives, key=lambda o: o["score"]["mean"]) if measured_objectives else None
        evidence_by_topic[topic_id] = {
            "score": (row.get("score") or {}).get("mean"),
            "weakest_objective": None if weakest is None else {
                "code": weakest["code"], "text_ru": weakest["text_ru"], "text_kz": weakest["text_kz"],
                "score": weakest["score"]["mean"],
            },
            "prerequisites": [{
                "code": p["code"], "topic_code": p["topic_code"], "text_ru": p["text_ru"], "text_kz": p["text_kz"],
                "score": (p.get("score") or {}).get("mean"), "confirmed": p["confirmed"],
            } for p in evidence["prerequisites"]],
        }
    topics = []
    if plan is not None:
        rows = list(session.scalars(select(m.PlanTopicHours).where(m.PlanTopicHours.plan_id == plan.id)))
        tmap = {t.id: t for t in session.scalars(select(m.Topic).where(m.Topic.id.in_([r.topic_id for r in rows])))}
        for r in sorted(rows, key=lambda r: tmap[r.topic_id].order_index):
            t = tmap[r.topic_id]
            ot = by_topic.get(t.id, {})
            if ot.get("deficit") is not None:
                prio, basis = round(ot["deficit"] / dmax, 3), "deficit"
            else:
                prio, basis = 0.5, "not_measured_default"
            protected = ot.get("status") in ("not_measured", "unverified_mapping", "insufficient_data")
            protection_ru = "Часы защищены от сокращения: сначала нужна диагностика."
            protection_kz = "Сағат қысқартудан қорғалған: алдымен диагностика қажет."
            facts = {**evidence_by_topic.get(t.id, {}), "status": ot.get("status"),
                     "title_ru": t.title_ru, "title_kz": t.title_kz,
                     "protected_from_reduction": protected,
                     "protection_reason_ru": protection_ru if protected else None,
                     "protection_reason_kz": protection_kz if protected else None}
            topics.append({
                "topic_id": t.id, "code": t.code, "title_ru": t.title_ru, "title_kz": t.title_kz,
                "current_hours": r.planned_hours, "elapsed_hours": r.elapsed_hours,
                "min_hours": max(r.min_hours or 0, r.planned_hours) if protected else r.min_hours,
                "max_hours": r.max_hours, "actual_hours": r.actual_hours, "priority": prio, "priority_basis": basis,
                "topic_status": ot.get("status"), "score": (ot.get("score") or {}).get("mean"),
                "recommend_diagnostic": protected, "protected_from_reduction": protected,
                "protection_reason_ru": protection_ru if protected else None,
                "protection_reason_kz": protection_kz if protected else None,
                "planning_facts": facts,
            })
        by_code = {t["code"]: t for t in topics}
        # A weak prerequisite inherits part of the priority of the difficult topic it enables.
        for target in topics:
            if target.get("score") is None or target["score"] >= 0.70:
                continue
            for prereq in target["planning_facts"].get("prerequisites", []):
                source = by_code.get(prereq["topic_code"])
                if source is None or prereq.get("score") is None or prereq["score"] >= 0.70:
                    continue
                support_priority = round(min(1.0, max(0.65, target["priority"] * 0.9)), 3)
                source["planning_facts"].setdefault("prerequisite_support_for", []).append({
                    "code": target["code"], "title_ru": target["title_ru"], "title_kz": target["title_kz"],
                    "score": target["score"],
                })
                if support_priority > source["priority"]:
                    source["priority"] = support_priority
                    source["priority_basis"] = "prerequisite_support"
    return {
        "plan": None if plan is None else {"id": plan.id, "name": plan.name, "scope": plan.scope, "horizon": plan.horizon,
                                           "name_kz": plan.name_kz or plan.name, "scope_kz": plan.scope_kz or plan.scope,
                                           "horizon_kz": plan.horizon_kz or plan.horizon,
                                           "version": plan.version, "status": plan.status, "plan_group_id": plan.plan_group_id},
        "topics": topics,
        "budget": sum(t["current_hours"] for t in topics),
        "priority_rule": "Приоритет основан на дефиците; слабый пререквизит получает поддержку от трудной темы. "
                         "Неизмеренные темы защищены от сокращения до диагностики.",
        "weights_version": "priority-weights-v1",
        "source_analysis_id": ov["context"]["analysis_id"],
        "is_calendar": False,
        "illustration_20h": {
            "budget": 20,
            "topics": [
                {"code": "R", "title": "Повторение", "current_hours": 4, "min_hours": 3, "priority": 0.2},
                {"code": "TARGET", "title": "Целевой трудный раздел", "current_hours": 8, "min_hours": 8, "max_hours": 10, "priority": 1.0},
                {"code": "CONS", "title": "Закрепление освоенного раздела", "current_hours": 4, "min_hours": 3, "priority": 0.2},
                {"code": "CHECK", "title": "Проверка и разбор", "current_hours": 4, "min_hours": 4, "priority": 0.5},
            ],
        },
    }


def solve(session: Session, org_id: str, req: PlanSolveRequest, user_id: str | None) -> dict:
    ds = an.get_dataset(session, org_id, req.dataset_id)
    for p in req.presets:
        if p not in PRESETS:
            raise ApiError("invalid_parameter", "Неизвестный сценарий", 422, {"allowed": list(PRESETS)})
    if not req.topics:
        raise ApiError("invalid_parameter", "Нет тем для планирования", 422)
    if req.time_limit_seconds <= 0 or req.time_limit_seconds > 30:
        raise ApiError("invalid_parameter", "Лимит времени 0–30 с", 422)
    if req.plan_id:
        plan = session.scalar(select(m.TeachingPlan).where(m.TeachingPlan.id == req.plan_id, m.TeachingPlan.org_id == org_id))
        if plan is None:
            raise not_found("plan", req.plan_id)
    trusted_context = plan_context(session, org_id, req.dataset_id, req.filters, user_id)
    trusted_topics = {t["topic_id"]: t for t in trusted_context["topics"]}
    constraints = []
    for t in req.topics:
        trusted = trusted_topics.get(t.topic_id or "", {})
        min_hours = t.min_hours
        if trusted.get("protected_from_reduction"):
            min_hours = max(t.current_hours, min_hours or 0)
        constraints.append(pl.TopicConstraint(
            topic_id=t.topic_id or f"block:{t.code}", code=t.code, title=t.title,
            current_hours=t.current_hours, priority=t.priority, min_hours=min_hours,
            max_hours=t.max_hours, fixed=t.fixed, elapsed_hours=t.elapsed_hours,
            max_change=t.max_change, evidence=trusted.get("planning_facts", {}),
        ))
    problem = pl.PlanProblem(
        topics=constraints,
        budget=req.budget, change_penalty=req.change_penalty, diminishing_rate=req.diminishing_rate,
        time_limit_seconds=req.time_limit_seconds,
    )

    # human names for conflict texts: trusted programme titles, otherwise the title sent with the topic block
    names = {t["code"]: (t["title_ru"], t["title_kz"]) for t in trusted_context["topics"]}
    for t in req.topics:
        names.setdefault(t.code, (t.title or t.code, t.title or t.code))

    def compute():
        scenarios = []
        for name in req.presets:
            scenario_problem = pl.preset(problem, name)
            res = pl.solve(scenario_problem)
            if name == "minimal_changes" and res.get("changes") and not any(c["delta"] for c in res["changes"]):
                # A conservative scenario must still answer the user's question when priorities clearly differ.
                retry = pl.preset(problem, name)
                retry.change_penalty = min(retry.change_penalty, 0.03)
                candidate = pl.solve(retry)
                if candidate.get("changes") and any(c["delta"] for c in candidate["changes"]):
                    res = candidate
                    res["minimal_change_retry"] = True
            res["preset"] = name
            res["status_message_ru"], res["status_message_kz"] = PLAN_STATUS[res["status"]]
            if (res.get("validation") or {}).get("valid"):
                res["verdict_ru"] = "Оптимальный план, ограничения проверены" if res["status"] == "optimal" else "Допустимый план, ограничения проверены"
                res["verdict_kz"] = "Оңтайлы жоспар, шектеулер тексерілді" if res["status"] == "optimal" else "Жарамды жоспар, шектеулер тексерілді"
                res["human_status"] = "ready"
            else:
                res["verdict_ru"] = res["status_message_ru"]
                res["verdict_kz"] = res["status_message_kz"]
                res["human_status"] = "needs_attention"
            res["technical_details"] = {
                "solver_status": res["status"], "method_version": res.get("method_version"),
                "weights_version": res.get("weights_version"), "objective": res.get("objective"),
                "objective_value": res.get("objective_value"), "solver": res.get("solver"),
                "minimal_change_retry": res.get("minimal_change_retry", False),
            }
            if res.get("conflict"):
                res["conflict"]["constraints"] = [
                    label_constraint({**c, "topic_title_ru": names.get(c.get("topic_code"), (None, None))[0],
                                      "topic_title_kz": names.get(c.get("topic_code"), (None, None))[1]})
                    for c in res["conflict"]["constraints"]]
            scenarios.append(res)
        return {"scenarios": scenarios, "budget": req.budget, "is_calendar": False,
                "input": {"topics": [t.model_dump() for t in req.topics], "change_penalty": req.change_penalty,
                          "diminishing_rate": req.diminishing_rate},
                "source_analysis_id": req.source_analysis_id,
                "note_ru": "План часов по темам; распределение по неделям — в «Календаре по неделям». Целевая функция распределяет "
                           "педагогический приоритет и не является прогнозом роста баллов."}

    params = req.model_dump(exclude={"filters", "dataset_id"})
    return an.persist_or_reuse(session, org_id, ds, "plan", req.filters.model_dump(), params, pl.METHOD_VERSION_PLANNER,
                               compute, user_id)
