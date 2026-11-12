"""Decision cards must be coherent: the action states the plan's hours, the material agrees with the comparison."""

from oqumap.services.decision_checks import states_hours
from oqumap.services.labels import leftover_internal


def _topic(curriculum, code):
    return next(t for t in curriculum["topics"] if t["code"] == code)


def _plan(c, H, ds, presets=("balanced", "focus_problem_topics")):
    ctx = c.get("/api/v1/plans/context", params={"dataset_id": ds}, headers=H).json()
    topics = [{"topic_id": t["topic_id"], "code": t["code"], "title": t["title_ru"], "current_hours": t["current_hours"],
               "priority": t["priority"], "min_hours": t["min_hours"], "max_hours": t["max_hours"],
               "elapsed_hours": t["elapsed_hours"]} for t in ctx["topics"]]
    return c.post("/api/v1/plans/solve", json={"dataset_id": ds, "topics": topics, "budget": ctx["budget"],
                                               "presets": list(presets)}, headers=H).json()


def _setup(client, H, datasets, curriculum):
    ds = datasets["base"]["id"]
    t3 = _topic(curriculum, "T3")["id"]
    ev = client.get(f"/api/v1/topics/{t3}/evidence", params={"dataset_id": ds}, headers=H).json()
    plan = _plan(client, H, ds)
    return ds, t3, ev, plan


def test_draft_states_hours_donors_and_stronger_edition(client, H, datasets, curriculum):
    ds, t3, ev, plan = _setup(client, H, datasets, curriculum)
    focus = next(s for s in plan["result"]["scenarios"] if s["preset"] == "focus_problem_topics")
    change = next(ch for ch in focus["changes"] if ch["code"] == "T3")
    rec = client.post("/api/v1/ai/recommend", json={"topic_analysis_id": ev["context"]["analysis_id"],
                                                     "plan_analysis_id": plan["context"]["analysis_id"],
                                                     "plan_preset": "focus_problem_topics"}, headers=H).json()
    out = rec["output"]
    assert rec["verification"]["numbers"]["status"] == "passed"
    assert states_hours(out["action"], change["delta"], change["before"], change["after"])
    assert f"{change['before']} → {change['after']} ч" in out["action"]
    for donor in (ch for ch in focus["changes"] if ch["delta"] < 0):
        assert f"(−{-donor['delta']} ч)" in out["action"]
    # material comes from the edition that is stronger in this topic, and the reason is stated
    assert out["material"]["kind"] == "stronger_edition" and out["material"]["favoured_edition_code"] == "EDB"
    assert "Пособие Б" in out["action"] and "сильнее в этой теме" in out["action"]
    srcs = [client.get(f"/api/v1/sources/{sid}", headers=H).json() for sid in out["citations"]]
    assert srcs and all(s["edition"]["code"] == "EDB" for s in srcs)
    # human words only
    text = " ".join(out[k] for k in ("problem", "hypothesis", "action", "check"))
    assert leftover_internal(text) == [] and "T3" not in text and "DEMO-M6" not in text
    kz = client.post("/api/v1/ai/recommend", json={"topic_analysis_id": ev["context"]["analysis_id"], "lang": "kz",
                                                    "plan_analysis_id": plan["context"]["analysis_id"],
                                                    "plan_preset": "focus_problem_topics"}, headers=H).json()["output"]
    assert "сағат" in kz["action"] and "Б оқу құралы" in kz["action"]


def _decision_body(ds, t3, ev, plan, action, source_ids, preset="balanced"):
    return {"dataset_id": ds, "topic_id": t3, "target_group": "Все классы", "problem": "Проблема", "hypothesis": "Гипотеза",
            "action": action, "responsible": "Методист", "analysis_ids": [ev["context"]["analysis_id"]],
            "plan_analysis_id": plan["context"]["analysis_id"], "plan_preset": preset, "source_ids": source_ids}


def test_contradictory_card_is_flagged_and_cannot_be_approved(client, H, datasets, curriculum):
    ds, t3, ev, plan = _setup(client, H, datasets, curriculum)
    client.post("/api/v1/comparisons/summary", json={"dataset_id": ds}, headers=H)  # edition verdict available
    eda = [s["source_id"] for s in ev["result"]["sources"] if s["edition_code"] == "EDA"][:1]
    body = _decision_body(ds, t3, ev, plan, "Добавить в план часы на тему и объяснять по пособию А, с. 14.", eda)
    chk = client.post("/api/v1/decisions/check", json=body, headers=H).json()
    codes = {x["code"] for x in chk["issues"]}
    assert chk["blocking"] and {"plan_hours_not_in_action", "material_contradicts_comparison"} <= codes
    msg = next(x for x in chk["issues"] if x["code"] == "material_contradicts_comparison")["message_ru"]
    assert "Пособие Б" in msg and "Пособие А" in msg
    d = client.post("/api/v1/decisions", json=body, headers=H).json()
    assert {x["code"] for x in d["coherence"]} >= {"plan_hours_not_in_action"}
    r = client.post(f"/api/v1/decisions/{d['id']}/approve", json={}, headers=H)
    assert r.status_code == 409 and r.json()["error"]["code"] == "decision_incoherent"


def test_explained_choice_of_the_other_edition_is_accepted(client, H, datasets, curriculum):
    ds, t3, ev, plan = _setup(client, H, datasets, curriculum)
    client.post("/api/v1/comparisons/summary", json={"dataset_id": ds}, headers=H)
    bal = next(s for s in plan["result"]["scenarios"] if s["preset"] == "balanced")
    ch = next(x for x in bal["changes"] if x["code"] == "T3")
    eda = [s["source_id"] for s in ev["result"]["sources"] if s["edition_code"] == "EDA"][:1]
    action = (f"Добавить {ch['delta']} ч ({ch['before']} → {ch['after']}). Используем пособие А, потому что в классах "
              "пособие Б пока недоступно.")
    chk = client.post("/api/v1/decisions/check", json=_decision_body(ds, t3, ev, plan, action, eda), headers=H).json()
    assert not chk["blocking"], chk


def test_coherent_draft_from_recommendation_is_approvable(client, H, datasets, curriculum):
    ds, t3, ev, plan = _setup(client, H, datasets, curriculum)
    rec = client.post("/api/v1/ai/recommend", json={"topic_analysis_id": ev["context"]["analysis_id"],
                                                     "plan_analysis_id": plan["context"]["analysis_id"],
                                                     "plan_preset": "balanced"}, headers=H).json()
    body = {**_decision_body(ds, t3, ev, plan, rec["output"]["action"], rec["citations"]),
            "problem": rec["output"]["problem"], "hypothesis": rec["output"]["hypothesis"],
            "generation_id": rec["generation_id"]}
    chk = client.post("/api/v1/decisions/check", json=body, headers=H).json()
    assert not chk["blocking"], chk
    d = client.post("/api/v1/decisions", json=body, headers=H).json()
    assert d["snapshot"]["recommendation"]["hours"]["delta"] == next(
        x for x in plan["result"]["scenarios"][0]["changes"] if x["code"] == "T3")["delta"]
    ap = client.post(f"/api/v1/decisions/{d['id']}/approve", json={}, headers=H)
    assert ap.status_code == 200, ap.text


def test_missing_analysis_and_hours_without_plan(client, H, datasets, curriculum):
    ds, t3, ev, plan = _setup(client, H, datasets, curriculum)
    body = {**_decision_body(ds, t3, ev, plan, "Добавить 2 часа на тему.", []), "plan_analysis_id": None,
            "analysis_ids": ["00000000-0000-0000-0000-000000000000"]}
    codes = {x["code"]: x["severity"] for x in client.post("/api/v1/decisions/check", json=body, headers=H).json()["issues"]}
    assert codes["analysis_missing"] == "critical" and codes["hours_without_plan"] == "warning" and codes["no_sources"] == "warning"


def test_states_hours_patterns():
    assert states_hours("Добавить 2 часа на тему (14 → 16 ч)", 2, 14, 16)
    assert states_hours("+2 ч на тему", 2)
    assert states_hours("тақырыбына 2 сағат қосу", 2)
    assert not states_hours("Добавить часы на тему", 2)
    assert not states_hours("Добавить 12 ч", 2)
