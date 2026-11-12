"""Programme-wide edition comparison: the verdict is computed from the per-topic rows, never written in advance."""

from types import SimpleNamespace

from oqumap.services.edition_summary import verdict
from oqumap.services.labels import Humanizer, TopicRef, edition_name, leftover_internal, match_topics


def _topic(curriculum, code):
    return next(t for t in curriculum["topics"] if t["code"] == code)


def test_summary_finds_topic_dependent_advantage_and_matches_single_topic(client, H, datasets, curriculum):
    ds = datasets["base"]["id"]
    r = client.post("/api/v1/comparisons/summary", json={"dataset_id": ds}, headers=H)
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    v = res["verdict"]
    assert v["kind"] == "topic_dependent"
    assert "T3" in v["b_topics"] and "T7" in v["a_topics"]
    assert v["raw_misleading"] is True and v["raw_story_ru"]
    # the verdict names topics and editions in words, never by internal code
    assert "Единого лучшего пособия нет" in v["text_ru"] and "Пособие Б" in v["text_ru"]
    assert "«Проценты»" in v["text_ru"] and leftover_internal(v["text_ru"]) == []
    assert "T3" not in v["text_ru"] and "EDB" not in v["text_ru"]
    assert v["text_kz"] and leftover_internal(v["text_kz"]) == []
    # each row is the same standardised comparison as the single-topic screen
    row = next(x for x in res["rows"] if x["code"] == "T3")
    eds = res["editions"]
    single = client.post("/api/v1/comparisons", json={"dataset_id": ds, "topic_id": _topic(curriculum, "T3")["id"],
                                                     "edition_a_id": eds["a"]["id"], "edition_b_id": eds["b"]["id"]},
                         headers=H).json()["result"]
    assert abs(row["adjusted_difference"] - single["adjusted"]["difference"]) < 1e-9
    assert row["ci"] == single["uncertainty"]["adjusted_difference_ci"]
    assert row["n"]["a"]["learners"] == single["raw"]["a"]["n_learners"]
    # unmeasured topics are not compared rather than shown as zero
    assert {"T6", "T8"} <= set(v["not_compared_topics"])
    assert eds["a"]["name_ru"] == "Пособие А" and eds["b"]["name_kz"] == "Б оқу құралы"


def test_summary_is_stored_and_reused(client, H, datasets):
    ds = datasets["base"]["id"]
    a = client.post("/api/v1/comparisons/summary", json={"dataset_id": ds}, headers=H).json()
    b = client.post("/api/v1/comparisons/summary", json={"dataset_id": ds}, headers=H).json()
    assert a["context"]["analysis_id"] == b["context"]["analysis_id"] and a["context"]["kind"] == "edition_summary"


def _row(code, favoured, diff, raw, status="comparable"):
    return {"code": code, "title_ru": f"Тема {code}", "title_kz": f"Тақырып {code}", "status": status, "favoured": favoured,
            "adjusted_difference": diff, "raw_difference": raw}


ED_A = SimpleNamespace(title="Учебник A", code="X1")
ED_B = SimpleNamespace(title="Учебник B", code="X2")


def test_verdict_kinds_follow_the_rows():
    assert verdict([_row("A1", "b", 0.05, 0.02), _row("A2", None, 0.01, 0.0)], ED_A, ED_B)["kind"] == "b_ahead"
    assert verdict([_row("A1", None, 0.01, -0.02)], ED_A, ED_B)["kind"] == "no_confirmed_difference"
    assert verdict([_row("A1", None, None, None, "not_comparable")], ED_A, ED_B)["kind"] == "insufficient"
    v = verdict([_row("A1", "b", 0.05, -0.03), _row("A2", "a", -0.04, -0.06)], ED_A, ED_B)
    assert v["kind"] == "topic_dependent" and v["raw_misleading"]
    assert "Учебник B сильнее" in v["text_ru"] and "учебник A — в теме" in v["text_ru"]


def test_edition_names_and_topic_matching():
    assert edition_name("Демонстрационное пособие А", "EDA") == "Пособие А"
    assert edition_name("Демонстрационное пособие Б", "EDB", "kz") == "Б оқу құралы"
    assert edition_name("Учебник A (synthetic)", "JURY-A") == "Учебник A"
    assert edition_name("Математика. 6 класс", "M6") == "Математика. 6 класс"
    topics = [TopicRef("T2", "Обыкновенные дроби: сокращение и сравнение", "Жай бөлшектер: қысқарту және салыстыру"),
              TopicRef("T3", "Сложение и вычитание дробей с разными знаменателями", "Бөлімдері әртүрлі бөлшектерді қосу және азайту"),
              TopicRef("T7", "Проценты", "Пайыздар")]
    assert [t.code for t in match_topics("сложение дробей", topics)] == ["T3"]
    assert [t.code for t in match_topics("за счёт процентов", topics)] == ["T7"]
    assert [t.code for t in match_topics("бөлшектерді қосу", topics)] == ["T3"]
    assert [t.code for t in match_topics("тема T2", topics)] == ["T2"]
    assert match_topics("погода", topics) == []


def test_humanizer_replaces_codes_and_detects_leftovers():
    h = Humanizer(topics={"T3": ("Сложение дробей", "Бөлшектерді қосу"), "T1": ("Делимость", "Бөлінгіштік")},
                  objectives={"DEMO-M6-3.2": ("Смешанные числа", "Аралас сандар")},
                  editions={"EDB": ("Пособие Б", "Б оқу құралы")})
    out = h.text("Тема T3: цель DEMO-M6-3.2 — 43,3%; EDB сильнее.")
    assert out == "«Сложение дробей»: цель «Смешанные числа» — 43,3%; Пособие Б сильнее."
    assert leftover_internal(out) == []
    assert leftover_internal("статус comparable, EDA") == ["comparable", "EDA"]


def test_graph_shows_edition_comparison_and_stronger_edition_first(client, H, datasets, curriculum):
    t3 = _topic(curriculum, "T3")
    g = client.get(f"/api/v1/topics/{t3['id']}/graph", params={"dataset_id": datasets["base"]["id"]}, headers=H).json()["result"]
    cmp_node = next(n for n in g["nodes"] if n["kind"] == "comparison")
    assert cmp_node["label_ru"].startswith("Пособие Б сильнее") and cmp_node["metrics"]["favoured"] == "EDB"
    assert cmp_node["id"] in g["path"]
    src = next(n for n in g["nodes"] if n["id"] in g["path"] and n["kind"] == "source")
    assert src["metrics"]["edition_code"] == "EDB" and src["metrics"]["stronger_edition"] is True
    # labels carry names only; codes stay in the "code" field
    for n in g["nodes"]:
        if n["kind"] in ("topic", "objective", "prerequisite", "item"):
            assert n["code"] not in n["label_ru"], n["label_ru"]
