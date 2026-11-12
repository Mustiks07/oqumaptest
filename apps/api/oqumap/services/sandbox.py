"""Decision Sandbox: compare 2–3 hour scenarios side by side with the current plan ("было").

A methodist describes an intent in plain words ("добавь 2 часа на T3 за счёт T7, T5 не трогать"); it is turned
into *typed* planner operations with a diff preview that the user confirms. Each scenario is solved by CP-SAT and
re-checked by the independent validator; the comparison shows hours, coverage of measured objectives,
prerequisite risks and other risks. The objective distributes pedagogical priority — it is not a forecast of
score gains. Results are stored as analysis runs (replayable by fingerprint) and can be turned into a decision.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..errors import ApiError
from . import analysis as an
from . import planning
from .labels import TopicRef, match_topics

METHOD_VERSION_SANDBOX = "sandbox-v1"
OPS = ("add", "remove", "set", "min", "max", "fix", "max_change", "priority", "budget")


OPS_SCHEMA = {"type": "object", "properties": {"ops": {"type": "array", "items": {
    "type": "object", "properties": {"op": {"type": "string", "enum": list(OPS)}, "topic": {"type": "string"}, "value": {"type": "number"}},
    "required": ["op"], "additionalProperties": False}}}, "required": ["ops"], "additionalProperties": False}


class Op(BaseModel):
    op: str
    topic: str | None = None  # topic code; None for budget / global max_change
    value: float | None = None


class Scenario(BaseModel):
    name: str
    ops: list[Op] = Field(default_factory=list)


class SandboxRequest(BaseModel):
    dataset_id: str
    scenarios: list[Scenario]
    filters: an.Filters = Field(default_factory=an.Filters)


class IntentRequest(BaseModel):
    dataset_id: str
    text: str
    base_ops: list[Op] = Field(default_factory=list)
    lang: str = "ru"


# ---------------------------------------------------------------------------
# Intent → typed operations
# ---------------------------------------------------------------------------

NUM = r"(\d{1,3})"
TOPIC = r"(T\d{1,2})"
PRI = r"(\d(?:[.,]\d+)?)"
PATTERNS: list[tuple[re.Pattern, callable]] = [
    (re.compile(rf"(?:добав\w*|увелич\w*|плюс|\+|қос\w*)\s*{NUM}\s*(?:ч\w*|сағ\w*)?\s*(?:на|к|для|по)?\s*(?:тем\w*\s*)?{TOPIC}", re.I),
     lambda g: [Op(op="add", topic=g[1].upper(), value=int(g[0]))]),
    (re.compile(rf"{TOPIC}\s*(?:на\s*)?\+\s*{NUM}", re.I), lambda g: [Op(op="add", topic=g[0].upper(), value=int(g[1]))]),
    (re.compile(rf"(?:за\s*сч[её]т|забрать\s*(?:у|из)|убав\w*\s*(?:у|в)?|сократ\w*|азайт\w*)\s*(?:тем\w*\s*)?{TOPIC}(?:\s*на\s*{NUM})?", re.I),
     lambda g: [Op(op="remove", topic=g[0].upper(), value=int(g[1]) if g[1] else None)]),
    (re.compile(rf"{TOPIC}\s*(?:не\s*(?:трогать|менять|трогай|меняй)|зафикс\w*|без\s*изменений|өзгертпе\w*)", re.I),
     lambda g: [Op(op="fix", topic=g[0].upper())]),
    (re.compile(rf"(?:не\s*(?:трогать|менять|трогай|меняй)|зафиксир\w*)\s*(?:тем\w*\s*)?{TOPIC}", re.I),
     lambda g: [Op(op="fix", topic=g[0].upper())]),
    (re.compile(rf"(?:на\s*)?{TOPIC}\s*(?:не\s*меньше|минимум|хотя\s*бы|от)\s*{NUM}", re.I),
     lambda g: [Op(op="min", topic=g[0].upper(), value=int(g[1]))]),
    (re.compile(rf"(?:не\s*меньше|минимум|хотя\s*бы)\s*{NUM}\s*(?:ч\w*)?\s*(?:на|для)\s*{TOPIC}", re.I),
     lambda g: [Op(op="min", topic=g[1].upper(), value=int(g[0]))]),
    (re.compile(rf"{TOPIC}\s*(?:не\s*больше|максимум|до)\s*{NUM}", re.I),
     lambda g: [Op(op="max", topic=g[0].upper(), value=int(g[1]))]),
    (re.compile(rf"{TOPIC}\s*(?:=|ровно)\s*{NUM}", re.I), lambda g: [Op(op="set", topic=g[0].upper(), value=int(g[1]))]),
    (re.compile(rf"(?:(?:каждую|любую)\s*тему\s*)?(?:изменени\w*|менять|изменять)\s*(?:не\s*больше|максимум|не\s*более)\s*(?:чем\s*на\s*)?{NUM}", re.I),
     lambda g: [Op(op="max_change", value=int(g[0]))]),
    (re.compile(rf"(?:бюджет|всего|итого)\s*{NUM}", re.I), lambda g: [Op(op="budget", value=int(g[0]))]),
    (re.compile(rf"(?:приоритет\w*)\s*{TOPIC}\s*{PRI}", re.I),
     lambda g: [Op(op="priority", topic=g[0].upper(), value=float(g[1].replace(",", ".")))]),
]


def parse_intent(text: str, topics: list[TopicRef] | None = None, ctx_topics: list[dict] | None = None) -> tuple[list[Op], list[str]]:
    """Codes are parsed by the rule patterns; leftover clauses are parsed by topic *name* when topics are given."""
    ops, leftovers = _parse_codes(text)
    if topics:
        still = []
        for chunk in leftovers:
            named = parse_named(chunk, topics, ctx_topics or [])
            donor_only = RE_DONOR.search(chunk) and not named
            added = [o for o in ops if o.op == "add"]
            if donor_only and added:  # ", пайыздар есебінен" / ", за счёт процентов" after the add clause
                donors = match_topics(chunk[RE_DONOR.search(chunk).end():] or chunk[:RE_DONOR.search(chunk).start()], topics)
                if donors:
                    total = int(sum(o.value or 0 for o in added))
                    share, rest = divmod(total, len(donors))
                    named = [Op(op="remove", topic=d.code, value=share + (1 if i < rest else 0)) for i, d in enumerate(donors)]
            if named:
                ops += named
            else:
                still.append(chunk)
        leftovers = still
        # a topic that is explicitly strengthened is never also lowered as a "stable" donor
        raised = {o.topic for o in ops if o.op in ("add", "set", "fix") or (o.op == "priority" and (o.value or 0) >= 1)}
        ops = [o for o in ops if not (o.op == "priority" and (o.value or 0) < 1 and o.topic in raised)]
    return ops, leftovers


def _parse_codes(text: str) -> tuple[list[Op], list[str]]:
    ops: list[Op] = []
    spans: list[tuple[int, int]] = []
    for pat, build in PATTERNS:
        for mt in pat.finditer(text):
            if any(a < mt.end() and mt.start() < b for a, b in spans):
                continue
            spans.append((mt.start(), mt.end()))
            ops += build(mt.groups())
    rest = text
    for a, b in sorted(spans, reverse=True):
        rest = rest[:a] + " " + rest[b:]
    leftovers = [w for w in re.split(r"[,;.]|\s+и\s+|\s+а\s+|\s+но\s+|\s+және\s+", rest) if re.search(r"\w{3,}", w)
                 and not re.fullmatch(r"\s*(пожалуйста|давай|сделай|часа?|часов|тема|темы)\s*", w, re.I)]
    # paired "add N to X за счёт Y": the removal takes the same N unless given
    adds = [o for o in ops if o.op == "add"]
    for o in ops:
        if o.op == "remove" and o.value is None:
            o.value = adds[0].value if adds else 1
    return ops, [w.strip() for w in leftovers]


# ---------------------------------------------------------------------------
# Plain-language clauses with topic *names* ("добавь 2 часа на сложение дробей за счёт процентов")
# ---------------------------------------------------------------------------

WORD_NUM = {"один": 1, "одну": 1, "одного": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7,
            "восемь": 8, "девять": 9, "десять": 10, "бір": 1, "екі": 2, "үш": 3, "төрт": 4, "бес": 5, "алты": 6, "жеті": 7,
            "сегіз": 8, "тоғыз": 9, "он": 10}
RE_DONOR = re.compile(r"\b(?:за\s*сч[её]т|из|забрать\s*(?:у|из))\b|есебінен", re.I)
RE_ADD = re.compile(r"добав|увелич|прибав|плюс|\bқос|арттыр", re.I)
RE_SET = re.compile(r"сдела|установ|ровно|сделать|\bжаса|болсын|\bету\b|\bқыл", re.I)
RE_REMOVE = re.compile(r"убер|убра|сократ|сним|снят|уменьш|азайт|қысқарт|алып\s*таста", re.I)
RE_FIX = re.compile(r"не\s*(?:трога|меня|измен)|оставь|оставить|зафикс|қозғама|өзгертпе|тиме", re.I)
RE_STRENGTHEN = re.compile(r"усил|укреп|күшейт|нығайт", re.I)
RE_STABLE = re.compile(r"устойчив|стабильн|сильн\w*\s*тем|освоенн|тұрақты|меңгерілген", re.I)
RE_MIN = re.compile(r"не\s*меньше|минимум|хотя\s*бы|кемінде", re.I)
RE_MAX = re.compile(r"не\s*больше|максимум|көп\s*дегенде", re.I)


def _number(text: str) -> int | None:
    m = re.search(r"\d{1,3}", text)
    if m:
        return int(m.group())
    for w in re.findall(r"[а-яёәғқңөұүһі]+", text.lower()):
        if w in WORD_NUM:
            return WORD_NUM[w]
    if re.search(r"\bчас\b|\bчасик|\bсағат\b", text.lower()):
        return 1  # "добавить час" = one hour
    return None


def stable_topics(ctx_topics: list[dict]) -> list[str]:
    """"Устойчивые темы": measured, not difficult, with a result above the median of measured topics (data-driven)."""
    measured = [t for t in ctx_topics if t.get("score") is not None and t.get("topic_status") in ("stable", "attention")]
    if not measured:
        return []
    scores = sorted(t["score"] for t in ctx_topics if t.get("score") is not None)
    median = scores[len(scores) // 2] if len(scores) % 2 else (scores[len(scores) // 2 - 1] + scores[len(scores) // 2]) / 2
    return [t["code"] for t in measured if t["score"] > median]


def parse_named(chunk: str, topics: list[TopicRef], ctx_topics: list[dict]) -> list[Op]:
    """One clause → typed ops, topics recognised by name. Returns [] when the clause is not understood."""
    donor_m = RE_DONOR.search(chunk)
    main, donor = (chunk[:donor_m.start()], chunk[donor_m.end():]) if donor_m else (chunk, "")
    n = _number(main)
    targets = match_topics(main, topics)
    donors = match_topics(donor, topics) if donor else []
    stable = stable_topics(ctx_topics) if RE_STABLE.search(chunk) else []
    prio = {t["code"]: t["priority"] for t in ctx_topics}
    ops: list[Op] = []
    if RE_STRENGTHEN.search(main) and targets:
        ops += [Op(op="priority", topic=t.code, value=1.0) for t in targets]
        if n:
            ops += [Op(op="add", topic=t.code, value=n) for t in targets]
    elif RE_FIX.search(main) and targets:
        ops += [Op(op="fix", topic=t.code) for t in targets]
    elif RE_MIN.search(main) and targets and n is not None:
        ops += [Op(op="min", topic=t.code, value=n) for t in targets]
    elif RE_MAX.search(main) and targets and n is not None:
        ops += [Op(op="max", topic=t.code, value=n) for t in targets]
    elif RE_SET.search(main) and targets and n is not None:
        ops += [Op(op="set", topic=t.code, value=n) for t in targets]
    elif RE_ADD.search(main) and targets and n is not None:
        ops += [Op(op="add", topic=t.code, value=n) for t in targets]
    elif RE_REMOVE.search(main) and (targets or stable):
        if stable and not targets:  # "убрать часы с устойчивых тем": they become preferred donors
            ops += [Op(op="priority", topic=c, value=round(min(prio.get(c, 0.5), 1.0) * 0.5, 3)) for c in stable]
        elif n is not None:
            ops += [Op(op="remove", topic=t.code, value=n) for t in targets]
    if ops and donors:
        added = sum(int(o.value or 0) for o in ops if o.op == "add")
        if added:
            share, rest = divmod(added, len(donors))
            ops += [Op(op="remove", topic=d.code, value=share + (1 if i < rest else 0)) for i, d in enumerate(donors)]
    return ops


def describe(ops: list[Op], names: dict[str, tuple[str, str]], lang: str = "ru") -> list[str]:
    """What was understood, in words (no internal codes): shown before anything is computed."""
    out = []
    for o in ops:
        nm = f"«{names.get(o.topic, (o.topic, o.topic))[0 if lang == 'ru' else 1]}»" if o.topic else ""
        v = None if o.value is None else (int(o.value) if float(o.value).is_integer() else o.value)
        if lang == "ru":
            txt = {"add": f"Добавить {v} ч: {nm}", "remove": f"Снять {v} ч: {nm}", "set": f"Установить {v} ч: {nm}",
                   "min": f"Не меньше {v} ч: {nm}", "max": f"Не больше {v} ч: {nm}", "fix": f"Не изменять часы: {nm}",
                   "priority": f"Приоритет {'повышен' if (v or 0) >= 1 else 'понижен'}: {nm}",
                   "budget": f"Общий бюджет: {v} ч", "max_change": f"Каждую тему менять не больше чем на {v} ч"}[o.op]
        else:
            txt = {"add": f"{nm}: {v} сағат қосу", "remove": f"{nm}: {v} сағат алу", "set": f"{nm}: {v} сағат белгілеу",
                   "min": f"{nm}: кемінде {v} сағ", "max": f"{nm}: көп дегенде {v} сағ", "fix": f"{nm}: сағатты өзгертпеу",
                   "priority": f"{nm}: басымдық {'артты' if (v or 0) >= 1 else 'төмендеді'}",
                   "budget": f"Жалпы бюджет: {v} сағ", "max_change": f"Әр тақырыпты {v} сағаттан артық өзгертпеу"}[o.op]
        out.append(txt)
    return out


def _base(session: Session, org_id: str, dataset_id: str, f: an.Filters, user_id: str | None) -> dict:
    ctx = planning.plan_context(session, org_id, dataset_id, f, user_id)
    if not ctx["topics"]:
        raise ApiError("no_plan", "В наборе нет учебного плана для песочницы", 422)
    return ctx


def apply_ops(ctx: dict, ops: list[Op]) -> tuple[list[dict], int, list[dict]]:
    """Returns (topic inputs, budget, diff rows). Unknown topic codes are rejected (typed constraints only)."""
    topics = {t["code"]: {"topic_id": t["topic_id"], "code": t["code"], "title": t["title_ru"], "current_hours": t["current_hours"],
                          "priority": t["priority"], "min_hours": t["min_hours"], "max_hours": t["max_hours"],
                          "fixed": False, "elapsed_hours": t["elapsed_hours"], "max_change": None, "target": None}
              for t in ctx["topics"]}
    budget = ctx["budget"]
    diff: list[dict] = []

    def rec(code, field, before, after):
        diff.append({"topic": code, "field": field, "before": before, "after": after})

    for o in ops:
        if o.op not in OPS:
            raise ApiError("invalid_op", "Неизвестная операция", 422, {"op": o.op, "allowed": list(OPS)})
        if o.op in ("budget", "max_change") and o.topic is None:
            if o.value is None or o.value < 0:
                raise ApiError("invalid_op", "Нужно неотрицательное значение", 422, {"op": o.op})
            if o.op == "budget":
                rec(None, "budget", budget, int(o.value))
                budget = int(o.value)
            else:
                for t in topics.values():
                    t["max_change"] = int(o.value)
                rec(None, "max_change", None, int(o.value))
            continue
        if o.topic not in topics:
            raise ApiError("unknown_topic", "Тема не найдена в плане", 422, {"topic": o.topic, "known": sorted(topics)})
        t = topics[o.topic]
        v = None if o.value is None else o.value
        if o.op in ("add", "remove", "set", "min", "max") and (v is None or v < 0 or v > 200):
            raise ApiError("invalid_op", "Значение часов вне диапазона", 422, {"op": o.op, "topic": o.topic})
        if o.op in ("add", "remove", "set"):
            cur = t["target"] if t["target"] is not None else t["current_hours"]
            new = cur + int(v) if o.op == "add" else max(0, cur - int(v)) if o.op == "remove" else int(v)
            t["target"] = new
            rec(o.topic, "target_hours", cur, new)
        elif o.op == "min":
            rec(o.topic, "min_hours", t["min_hours"], int(v))
            t["min_hours"] = int(v)
        elif o.op == "max":
            rec(o.topic, "max_hours", t["max_hours"], int(v))
            t["max_hours"] = int(v)
        elif o.op == "fix":
            rec(o.topic, "fixed", False, True)
            t["fixed"] = True
        elif o.op == "priority":
            if v is None or not 0 <= v <= 1:
                raise ApiError("invalid_op", "Приоритет 0–1", 422, {"topic": o.topic})
            rec(o.topic, "priority", t["priority"], v)
            t["priority"] = v
    out = []
    for t in topics.values():
        tgt = t.pop("target")
        if tgt is not None:
            # the requested target becomes hard bounds, but never silently overrides the plan's own limits:
            # a target outside [min, max] stays a conflict that the solver reports and explains
            lo, hi = t["min_hours"], t["max_hours"]
            t["min_hours"] = tgt if lo is None or tgt >= lo else lo
            t["max_hours"] = tgt if hi is None or tgt <= hi else hi
            if t["min_hours"] > t["max_hours"]:
                t["min_hours"] = tgt
        out.append(t)
    return out, budget, diff


def preview(session: Session, org_id: str, req: IntentRequest, user_id: str | None) -> dict:
    if len(req.text) > 500:
        raise ApiError("too_long", "Слишком длинный запрос", 422)
    ctx = _base(session, org_id, req.dataset_id, an.Filters(), user_id)
    refs = [TopicRef(t["code"], t["title_ru"], t["title_kz"]) for t in ctx["topics"]]
    names = {t["code"]: (t["title_ru"], t["title_kz"]) for t in ctx["topics"]}
    ops, leftovers = parse_intent(req.text, refs, ctx["topics"])
    mode = "template"
    if leftovers:  # the rules did not understand everything: a live model may fill the same strict schema
        from ..ai.tasks import _live_or_none

        data, lm = _live_or_none(
            "sandbox_intent",
            "Переведи пожелание методиста о часах в операции планировщика. Темы — только коды из списка topics "
            "(сопоставь по названию). Операции: add/remove/set/min/max/fix/max_change/priority/budget; value — часы "
            "(priority — от 0 до 1). Ничего не придумывай: если фрагмент непонятен, не создавай для него операцию. "
            "Модель не меняет план: результат проверяет решатель и независимый валидатор. Ответ строго JSON.",
            {"text": req.text, "already_understood": [o.model_dump() for o in ops],
             "topics": [{"code": t["code"], "title_ru": t["title_ru"], "title_kz": t["title_kz"], "status": t["topic_status"],
                         "score": t["score"], "current_hours": t["current_hours"], "min_hours": t["min_hours"],
                         "max_hours": t["max_hours"]} for t in ctx["topics"]]},
            OPS_SCHEMA, synthetic=bool(an.get_dataset(session, org_id, req.dataset_id).is_synthetic))
        if data is not None:
            model_ops = []
            for o in data.get("ops", [])[:12]:
                try:
                    op = Op(**o)
                    apply_ops(ctx, [op])  # each op must be valid on its own (known topic, value in range)
                    model_ops.append(op)
                except (ApiError, ValueError, TypeError):
                    continue
            if model_ops:
                ops, leftovers, mode = model_ops, [], lm["mode"]
    all_ops = req.base_ops + ops
    _, _, diff = apply_ops(ctx, all_ops)  # validates topics/values; raises on unknown topic
    for row in diff:
        row["title_ru"], row["title_kz"] = names.get(row["topic"], (None, None)) if row["topic"] else (None, None)
    return {"ops": [o.model_dump() for o in ops], "all_ops": [o.model_dump() for o in all_ops], "diff": diff,
            "understood_ru": describe(ops, names, "ru"), "understood_kz": describe(ops, names, "kz"),
            "not_understood": leftovers, "mode": mode,
            "note_ru": "Запрос переведён в типизированные ограничения планировщика. Проверьте изменения перед расчётом.",
            "note_kz": "Сұраныс жоспарлаушының типтелген шектеулеріне аударылды. Есептеу алдында өзгерістерді тексеріңіз."}


def run(session: Session, org_id: str, req: SandboxRequest, user_id: str | None) -> dict:
    if not 1 <= len(req.scenarios) <= 3:
        raise ApiError("invalid_parameter", "От 1 до 3 сценариев", 422)
    ds = an.get_dataset(session, org_id, req.dataset_id)
    ctx = _base(session, org_id, req.dataset_id, req.filters, user_id)
    measured = {t["code"]: t for t in ctx["topics"]}
    # prerequisites between topics (via objective relations)
    meta = an.load_meta(session, org_id, req.dataset_id)
    obj_topic = {o.id: o.topic_id for o in meta.objectives}
    code_of = {t.id: t.code for t in meta.topics}
    rels = list(session.scalars(select(m.ObjectiveRelation).where(m.ObjectiveRelation.target_objective_id.in_(list(obj_topic)))))
    prereq_of: dict[str, set[str]] = {}
    for r in rels:
        a, b = code_of.get(obj_topic.get(r.source_objective_id)), code_of.get(obj_topic.get(r.target_objective_id))
        if a and b and a != b:
            prereq_of.setdefault(a, set()).add(b)
    n_obj = {t.code: sum(1 for o in meta.objectives if o.topic_id == t.id) for t in meta.topics}

    def compute():
        cols = []
        for sc in req.scenarios:
            topics, budget, diff = apply_ops(ctx, sc.ops)
            body = planning.PlanSolveRequest(dataset_id=req.dataset_id, filters=req.filters, topics=[planning.TopicInput(**t) for t in topics],
                                             budget=budget, presets=["balanced"], source_analysis_id=ctx["source_analysis_id"])
            pr = planning.solve(session, org_id, body, user_id)
            res = pr["result"]["scenarios"][0]
            col = {"name": sc.name[:60], "ops": [o.model_dump() for o in sc.ops], "diff": diff, "status": res["status"],
                   "status_message_ru": res["status_message_ru"], "status_message_kz": res["status_message_kz"], "plan_analysis_id": pr["context"]["analysis_id"],
                   "budget": budget, "conflict": res.get("conflict"), "validation": res.get("validation")}
            if res["status"] in ("optimal", "feasible"):
                hours = {c["code"]: c["after"] for c in res["changes"]}
                col["hours"] = hours
                col["metrics"] = _metrics(hours, measured, prereq_of, n_obj)
            cols.append(col)
        before = {t["code"]: t["current_hours"] for t in ctx["topics"]}
        return {"before": {"hours": before, "metrics": _metrics(before, measured, prereq_of, n_obj), "budget": ctx["budget"]},
                "scenarios": cols, "topics": [{"code": t["code"], "title_ru": t["title_ru"], "title_kz": t["title_kz"],
                                               "status": t["topic_status"], "score": t["score"]} for t in ctx["topics"]],
                "is_calendar": False, "is_forecast": False,
                "note_ru": "Сравниваются распределения часов и риски. Это не прогноз роста баллов и не расписание по неделям."}

    params = {"scenarios": [s.model_dump() for s in req.scenarios]}
    return an.persist_or_reuse(session, org_id, ds, "sandbox", req.filters.model_dump(), params, METHOD_VERSION_SANDBOX, compute, user_id)


def _metrics(hours: dict[str, int], measured: dict[str, dict], prereq_of: dict[str, set[str]], n_obj: dict[str, int]) -> dict:
    weak = {c for c, t in measured.items() if t["topic_status"] == "difficult"}
    risks = []
    covered = 0
    total = 0
    for c, t in measured.items():
        h = hours.get(c, 0)
        total += n_obj.get(c, 0)
        if h > 0 and (t["min_hours"] is None or h >= t["min_hours"]):
            covered += n_obj.get(c, 0)
        if c in weak and h < t["current_hours"]:
            risks.append({"code": "weak_topic_reduced", "topic": c, "text_ru": f"Трудной теме «{t['title_ru']}» сокращены часы",
                          "text_kz": f"Қиын «{t['title_kz']}» тақырыбының сағаты қысқарды"})
        if t["topic_status"] in ("not_measured", "unverified_mapping", "insufficient_data") and h != t["current_hours"]:
            risks.append({"code": "change_without_evidence", "topic": c,
                          "text_ru": f"Часы темы «{t['title_ru']}» меняются без надёжных данных",
                          "text_kz": f"«{t['title_kz']}» тақырыбының сағаты сенімді деректерсіз өзгереді"})
    prereq_risks = []
    for a, targets in prereq_of.items():
        if a in hours and a in measured and hours[a] < measured[a]["current_hours"] and targets & weak:
            dep = sorted(targets & weak)
            prereq_risks.append({"code": "prerequisite_reduced", "topic": a, "for": dep,
                                 "text_ru": f"Сокращена опорная тема «{measured[a]['title_ru']}» для трудных тем "
                                            + ", ".join(f"«{measured[x]['title_ru']}»" for x in dep if x in measured),
                                 "text_kz": f"Қиын тақырыптар үшін тірек «{measured[a]['title_kz']}» тақырыбы қысқарды"})
    weak_hours = sum(hours.get(c, 0) for c in weak)
    return {"objective_coverage": {"covered": covered, "total": total}, "weak_topics": sorted(weak),
            "hours_on_weak_topics": weak_hours, "total_hours": sum(hours.values()),
            "risks": risks, "prerequisite_risks": prereq_risks}
