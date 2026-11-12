"""Hours allocation under constraints (OR-Tools CP-SAT) with an independent validator.

The objective distributes *pedagogical priority* with diminishing returns and penalises changes. It is a
planning device, not a forecast of score gains (docs/METHODOLOGY.md §6).

    maximize  sum_t p_t * U(h_t)  -  lambda * sum_t |h_t - h0_t|
    U(h) = (1 - r^h) / (1 - r)                         (concave, r in (0,1))
    default r = 0.5^(1/mean(h0)): the marginal value of an hour halves at the average topic size, so the
    objective is scale-free with respect to the size of the plan.

Constraints: integer hours, sum(h) = budget, min/max per topic, fixed topics, elapsed hours cannot be
removed (h_t >= elapsed_t), optional max change per topic. The plan is a per-topic hours plan, not a
weekly calendar.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from ortools.sat.python import cp_model

METHOD_VERSION_PLANNER = "planner-v1"
OBJECTIVE_SCALE = 1000


@dataclass
class TopicConstraint:
    topic_id: str
    code: str
    current_hours: int
    priority: float = 1.0
    min_hours: int | None = None
    max_hours: int | None = None
    fixed: bool = False
    elapsed_hours: int = 0
    max_change: int | None = None
    title: str = ""
    evidence: dict = field(default_factory=dict)


@dataclass
class PlanProblem:
    topics: list[TopicConstraint]
    budget: int
    change_penalty: float = 0.05  # lambda, in priority-utility units per hour moved
    diminishing_rate: float | None = None  # r; None => 0.5 ** (1 / mean current hours)
    time_limit_seconds: float = 5.0
    weights_version: str = "priority-weights-v1"
    meta: dict = field(default_factory=dict)


@dataclass
class Violation:
    constraint: str
    topic_code: str | None
    detail: dict

    def as_dict(self) -> dict:
        return asdict(self)


def effective_rate(problem: PlanProblem) -> float:
    if problem.diminishing_rate is not None:
        return problem.diminishing_rate
    hs = [t.current_hours for t in problem.topics if t.current_hours > 0]
    mean_h = sum(hs) / len(hs) if hs else 1.0
    return 0.5 ** (1.0 / max(mean_h, 1.0))


def utility(h: int, r: float) -> float:
    return (1 - r**h) / (1 - r)


def validate_plan(problem: PlanProblem, hours: dict[str, int]) -> list[Violation]:
    """Independent check of every constraint; does not use the solver."""
    out: list[Violation] = []
    total = 0
    for t in problem.topics:
        if t.topic_id not in hours:
            out.append(Violation("missing_topic", t.code, {}))
            continue
        h = hours[t.topic_id]
        if not isinstance(h, int) or isinstance(h, bool):
            out.append(Violation("non_integer", t.code, {"value": h}))
            continue
        total += h
        if h < 0:
            out.append(Violation("negative", t.code, {"value": h}))
        if t.min_hours is not None and h < t.min_hours:
            out.append(Violation("min_hours", t.code, {"value": h, "min": t.min_hours}))
        if t.max_hours is not None and h > t.max_hours:
            out.append(Violation("max_hours", t.code, {"value": h, "max": t.max_hours}))
        if t.fixed and h != t.current_hours:
            out.append(Violation("fixed", t.code, {"value": h, "required": t.current_hours}))
        if h < t.elapsed_hours:
            out.append(Violation("elapsed_hours", t.code, {"value": h, "elapsed": t.elapsed_hours}))
        if t.max_change is not None and abs(h - t.current_hours) > t.max_change:
            out.append(Violation("max_change", t.code, {"value": h, "current": t.current_hours, "max_change": t.max_change}))
    extra = set(hours) - {t.topic_id for t in problem.topics}
    for e in extra:
        out.append(Violation("unknown_topic", None, {"topic_id": e}))
    if total != problem.budget:
        out.append(Violation("budget", None, {"total": total, "budget": problem.budget}))
    return out


def objective_value(problem: PlanProblem, hours: dict[str, int]) -> float:
    r = effective_rate(problem)
    v = 0.0
    for t in problem.topics:
        h = hours[t.topic_id]
        v += t.priority * utility(h, r) - problem.change_penalty * abs(h - t.current_hours)
    return v


# ---------------------------------------------------------------------------
# Model construction with one enforcement literal per constraint (for conflict explanation)
# ---------------------------------------------------------------------------


@dataclass
class _Built:
    model: cp_model.CpModel
    h: dict[str, cp_model.IntVar]
    lits: dict[str, cp_model.IntVar]
    labels: dict[str, dict]


def _build(problem: PlanProblem, with_objective: bool) -> _Built:
    m = cp_model.CpModel()
    H = max(problem.budget, 0)
    ub = max(H, max((t.current_hours for t in problem.topics), default=0))
    h = {t.topic_id: m.NewIntVar(0, ub, f"h_{t.code}") for t in problem.topics}
    lits: dict[str, cp_model.IntVar] = {}
    labels: dict[str, dict] = {}

    def lit(key: str, label: dict) -> cp_model.IntVar:
        b = m.NewBoolVar(key)
        lits[key] = b
        labels[key] = label
        return b

    b = lit("budget", {"constraint": "budget", "topic_code": None, "value": problem.budget})
    m.Add(sum(h.values()) == problem.budget).OnlyEnforceIf(b)
    for t in problem.topics:
        if t.min_hours is not None:
            m.Add(h[t.topic_id] >= t.min_hours).OnlyEnforceIf(
                lit(f"min:{t.code}", {"constraint": "min_hours", "topic_code": t.code, "value": t.min_hours})
            )
        if t.max_hours is not None:
            m.Add(h[t.topic_id] <= t.max_hours).OnlyEnforceIf(
                lit(f"max:{t.code}", {"constraint": "max_hours", "topic_code": t.code, "value": t.max_hours})
            )
        if t.fixed:
            m.Add(h[t.topic_id] == t.current_hours).OnlyEnforceIf(
                lit(f"fixed:{t.code}", {"constraint": "fixed", "topic_code": t.code, "value": t.current_hours})
            )
        if t.elapsed_hours > 0:
            m.Add(h[t.topic_id] >= t.elapsed_hours).OnlyEnforceIf(
                lit(f"elapsed:{t.code}", {"constraint": "elapsed_hours", "topic_code": t.code, "value": t.elapsed_hours})
            )
        if t.max_change is not None:
            k = lit(f"change:{t.code}", {"constraint": "max_change", "topic_code": t.code, "value": t.max_change})
            m.Add(h[t.topic_id] - t.current_hours <= t.max_change).OnlyEnforceIf(k)
            m.Add(t.current_hours - h[t.topic_id] <= t.max_change).OnlyEnforceIf(k)

    if with_objective:
        r = effective_rate(problem)
        terms = []
        for t in problem.topics:
            table = [int(round(OBJECTIVE_SCALE * t.priority * utility(k, r))) for k in range(ub + 1)]
            u = m.NewIntVar(min(table), max(table), f"u_{t.code}")
            m.AddElement(h[t.topic_id], table, u)
            d = m.NewIntVar(0, ub, f"d_{t.code}")
            m.AddAbsEquality(d, h[t.topic_id] - t.current_hours)
            terms.append(u - int(round(OBJECTIVE_SCALE * problem.change_penalty)) * d)
        m.Maximize(sum(terms))
    return _Built(m, h, lits, labels)


def _feasible_with(problem: PlanProblem, keys: list[str], time_limit: float) -> str:
    built = _build(problem, with_objective=False)
    for k, b in built.lits.items():
        if k not in keys:
            built.model.Add(b == 0)  # constraint switched off
    built.model.AddAssumptions([built.lits[k] for k in keys])
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 1
    st = solver.Solve(built.model)
    return {cp_model.OPTIMAL: "feasible", cp_model.FEASIBLE: "feasible", cp_model.INFEASIBLE: "infeasible"}.get(st, "unknown")


def explain_infeasibility(problem: PlanProblem, time_limit: float = 2.0) -> dict:
    """Return a verified minimal set of mutually incompatible constraints.

    1) CP-SAT returns a sufficient set of assumptions; 2) deletion-based minimisation; each removal is
    re-solved, so every listed constraint is necessary for the conflict (verified, not narrated)."""
    built = _build(problem, with_objective=False)
    built.model.AddAssumptions(list(built.lits.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 1
    st = solver.Solve(built.model)
    if st != cp_model.INFEASIBLE:
        return {"verified": False, "reason": "not_proven_infeasible", "constraints": []}
    idx_to_key = {b.Index(): k for k, b in built.lits.items()}
    core = [idx_to_key[i] for i in solver.SufficientAssumptionsForInfeasibility() if i in idx_to_key]
    if not core or _feasible_with(problem, core, time_limit) != "infeasible":
        core = list(built.lits)
    i = 0
    while i < len(core):
        trial = core[:i] + core[i + 1 :]
        if trial and _feasible_with(problem, trial, time_limit) == "infeasible":
            core = trial
        else:
            i += 1
    verified = _feasible_with(problem, core, time_limit) == "infeasible" and all(
        _feasible_with(problem, core[:j] + core[j + 1 :], time_limit) == "feasible" for j in range(len(core))
    )
    by_code = {t.code: t for t in problem.topics}
    items = []
    lower, upper = 0, 0
    for k in core:
        lab = dict(built.labels[k])
        items.append({"key": k, **lab})
    # Arithmetic summary over topics, using only constraints in the core.
    if "budget" in core:
        for t in problem.topics:
            lo, hi = 0, None
            for k in core:
                lab = built.labels[k]
                if lab["topic_code"] != t.code:
                    continue
                if lab["constraint"] in ("min_hours", "elapsed_hours"):
                    lo = max(lo, lab["value"])
                elif lab["constraint"] == "max_hours":
                    hi = lab["value"] if hi is None else min(hi, lab["value"])
                elif lab["constraint"] == "fixed":
                    lo = max(lo, lab["value"])
                    hi = lab["value"] if hi is None else min(hi, lab["value"])
                elif lab["constraint"] == "max_change":
                    cur = by_code[t.code].current_hours
                    lo = max(lo, cur - lab["value"])
                    hi = cur + lab["value"] if hi is None else min(hi, cur + lab["value"])
            lower += lo
            upper = None if (upper is None or hi is None) else upper + hi
            if hi is None:
                upper = None
    arithmetic = None
    if "budget" in core:
        arithmetic = {"budget": problem.budget, "sum_lower_bounds": lower, "sum_upper_bounds": upper}
    return {"verified": verified, "constraints": items, "arithmetic": arithmetic}


_STATUS = {
    cp_model.OPTIMAL: "optimal",
    cp_model.FEASIBLE: "feasible",
    cp_model.INFEASIBLE: "infeasible",
    cp_model.UNKNOWN: "unknown",
    cp_model.MODEL_INVALID: "invalid",
}


def solve(problem: PlanProblem) -> dict:
    pre_errors = _input_errors(problem)
    if pre_errors:
        return {"status": "invalid", "input_errors": pre_errors, "hours": None, "method_version": METHOD_VERSION_PLANNER}
    built = _build(problem, with_objective=True)
    for b in built.lits.values():
        built.model.Add(b == 1)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = problem.time_limit_seconds
    solver.parameters.num_workers = 4
    solver.parameters.random_seed = 7
    st = solver.Solve(built.model)
    status = _STATUS.get(st, "unknown")
    result: dict = {
        "status": status,
        "method_version": METHOD_VERSION_PLANNER,
        "weights_version": problem.weights_version,
        "objective": {
            "formula": "maximize Σ p_t·(1−r^h_t)/(1−r) − λ·Σ|h_t − h0_t|",
            "change_penalty": problem.change_penalty,
            "diminishing_rate": round(effective_rate(problem), 6),
            "diminishing_rate_rule": "explicit" if problem.diminishing_rate is not None else "0.5^(1/mean(h0))",
            "is_forecast": False,
        },
        "solver": {"name": "OR-Tools CP-SAT", "wall_time_seconds": round(solver.WallTime(), 4),
                   "time_limit_seconds": problem.time_limit_seconds},
        "hours": None,
        "validation": None,
        "conflict": None,
    }
    if status in ("optimal", "feasible"):
        hours = {tid: int(solver.Value(v)) for tid, v in built.h.items()}
        violations = validate_plan(problem, hours)
        if violations:
            # Should never happen; never present an invalid plan as a solution.
            result["status"] = "invalid"
            result["validation"] = {"valid": False, "violations": [v.as_dict() for v in violations]}
            return result
        result["hours"] = hours
        result["objective_value"] = round(objective_value(problem, hours), 6)
        result["validation"] = {"valid": True, "violations": []}
        result["changes"] = [
            {
                "topic_id": t.topic_id,
                "code": t.code,
                "title": t.title,
                "before": t.current_hours,
                "after": hours[t.topic_id],
                "delta": hours[t.topic_id] - t.current_hours,
                "priority": t.priority,
                **_change_explanation(t, hours[t.topic_id], problem.topics, hours),
            }
            for t in problem.topics
        ]
        result["total_before"] = sum(t.current_hours for t in problem.topics)
        result["total_after"] = sum(hours.values())
    elif status == "infeasible":
        result["conflict"] = explain_infeasibility(problem)
    return result


def _pct(value: float | None) -> str | None:
    return None if value is None else f"{100 * value:.1f}".replace(".", ",") + "%"


def _change_explanation(topic: TopicConstraint, after: int, topics: list[TopicConstraint],
                        hours: dict[str, int]) -> dict:
    """Human, evidence-linked rationale for every row of the proposed plan."""
    delta = after - topic.current_hours
    facts = topic.evidence or {}
    score = _pct(facts.get("score"))
    weak = facts.get("weakest_objective") or {}
    weak_score = _pct(weak.get("score"))
    prereqs = [p for p in facts.get("prerequisites", []) if p.get("score") is not None and p["score"] < 0.70]
    recipients = [t for t in topics if hours[t.topic_id] > t.current_hours]
    recipient_names_ru = ", ".join((t.evidence or {}).get("title_ru") or t.title or t.code for t in recipients[:2])
    recipient_names_kz = ", ".join((t.evidence or {}).get("title_kz") or t.title or t.code for t in recipients[:2])

    if delta > 0:
        parts_ru = [f"Добавить {delta} ч."]
        parts_kz = [f"{delta} сағат қосу."]
        support = facts.get("prerequisite_support_for") or []
        if support:
            targets = ", ".join(x.get("title_ru") or x.get("code", "") for x in support[:2])
            targets_kz = ", ".join(x.get("title_kz") or x.get("code", "") for x in support[:2])
            parts_ru.append(f"Тема укрепляет пререквизит для трудного раздела «{targets}».")
            parts_kz.append(f"Тақырып «{targets_kz}» қиын бөлімі үшін пререквизитті нығайтады.")
        if score:
            parts_ru.append(f"Текущий результат — {score}.")
            parts_kz.append(f"Ағымдағы нәтиже — {score}.")
        if weak and weak_score:
            parts_ru.append(f"Самая слабая цель «{weak.get('text_ru') or weak.get('code')}» — {weak_score}.")
            parts_kz.append(f"Ең әлсіз мақсат «{weak.get('text_kz') or weak.get('code')}» — {weak_score}.")
        if prereqs:
            p = prereqs[0]
            ps = _pct(p.get("score"))
            parts_ru.append(f"Слабая основа «{p.get('text_ru') or p.get('code')}» — {ps}; её нужно поддержать вместе с темой.")
            parts_kz.append(f"«{p.get('text_kz') or p.get('code')}» әлсіз негізі — {ps}; оны тақырыппен бірге қолдау керек.")
        return {"reason_kind": "investment", "reason_ru": " ".join(parts_ru), "reason_kz": " ".join(parts_kz),
                "evidence": facts, "donor_reason_ru": None, "donor_reason_kz": None}

    if delta < 0:
        amount = abs(delta)
        parts_ru = [f"Высвободить {amount} ч для темы «{recipient_names_ru}»." if recipient_names_ru else f"Высвободить {amount} ч."]
        parts_kz = [f"«{recipient_names_kz}» тақырыбына {amount} сағат босату." if recipient_names_kz else f"{amount} сағат босату."]
        if score:
            parts_ru.append(f"Тема-донор показывает {score}; её нижняя граница и уже проведённые часы соблюдены.")
            parts_kz.append(f"Донор-тақырып нәтижесі {score}; төменгі шек пен өткізілген сағаттар сақталды.")
        else:
            parts_ru.append("Выбор донора основан на меньшем приоритете; все ограничения проверены.")
            parts_kz.append("Донор төменірек басымдық бойынша таңдалды; барлық шектеулер тексерілді.")
        reason_ru, reason_kz = " ".join(parts_ru), " ".join(parts_kz)
        return {"reason_kind": "donor", "reason_ru": reason_ru, "reason_kz": reason_kz, "evidence": facts,
                "donor_reason_ru": reason_ru, "donor_reason_kz": reason_kz}

    if facts.get("protected_from_reduction"):
        reason_ru = facts.get("protection_reason_ru") or "Часы сохранены: сначала нужна диагностика."
        reason_kz = facts.get("protection_reason_kz") or "Сағат сақталды: алдымен диагностика қажет."
        kind = "protected"
    else:
        reason_ru = "Часы сохранены: изменение не даёт дополнительной ценности при текущем бюджете и ограничениях."
        reason_kz = "Сағат сақталды: ағымдағы бюджет пен шектеулерде өзгеріс қосымша құндылық бермейді."
        kind = "unchanged"
    return {"reason_kind": kind, "reason_ru": reason_ru, "reason_kz": reason_kz, "evidence": facts,
            "donor_reason_ru": None, "donor_reason_kz": None}


def _input_errors(problem: PlanProblem) -> list[dict]:
    errs = []
    if problem.budget < 0:
        errs.append({"code": "negative_budget"})
    if problem.diminishing_rate is not None and not (0 < problem.diminishing_rate < 1):
        errs.append({"code": "bad_diminishing_rate"})
    if problem.change_penalty < 0 or not math.isfinite(problem.change_penalty):
        errs.append({"code": "bad_change_penalty"})
    seen = set()
    for t in problem.topics:
        if t.topic_id in seen:
            errs.append({"code": "duplicate_topic", "topic_code": t.code})
        seen.add(t.topic_id)
        if t.current_hours < 0 or t.elapsed_hours < 0:
            errs.append({"code": "negative_hours", "topic_code": t.code})
        if t.priority < 0 or not math.isfinite(t.priority):
            errs.append({"code": "bad_priority", "topic_code": t.code})
    return errs


def preset(problem: PlanProblem, name: str) -> PlanProblem:
    """Scenario presets shown to the methodist (weights stay visible and editable)."""
    import copy

    p = copy.deepcopy(problem)
    if name == "minimal_changes":
        # Keep the plan conservative without making the current allocation an automatic empty answer.
        p.change_penalty = round(max(min(problem.change_penalty * 1.4, 0.08), 0.06), 4)
    elif name == "focus_problem_topics":
        p.change_penalty = round(min(problem.change_penalty / 3, 0.015), 4)
    elif name == "balanced":
        pass
    else:
        raise ValueError(name)
    p.meta = {**problem.meta, "preset": name}
    return p
