"""The assistant answers the case questions directly, with computed facts and without internal codes.

Template mode is deterministic. The live path is exercised with a mock provider (no network, no key): the model
calls the same typed tools, its numbers are verified and internal codes in its text are replaced or rejected.
"""

import re

from oqumap.services.labels import leftover_internal


def ask(client, H, ds, question, lang="ru", **ctx):
    r = client.post("/api/v1/assistant/query", json={"question": question, "lang": lang,
                                                     "context": {"dataset_id": ds, **ctx}}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def _no_codes(text):
    assert leftover_internal(text) == [], text
    assert not re.search(r"\bT\d\b|DEMO-M6|\bED[AB]\b|comparable|adjusted_association", text), text


def test_hours_question_gets_number_reasons_and_donor(client, H, datasets):
    ds = datasets["base"]["id"]
    r = ask(client, H, ds, "Сколько часов добавить на сложение дробей и почему?")
    text = r["output"]["text"]
    assert r["verification"]["numbers"]["status"] == "passed"
    m = re.search(r"Рекомендуется добавить (\d+) час\w* на тему «Сложение и вычитание дробей с разными знаменателями» \((\d+) → (\d+) ч\)", text)
    assert m, text
    assert int(m.group(3)) - int(m.group(2)) == int(m.group(1))
    assert "47,1%" in text and "«Складывать и вычитать смешанные числа» — 43,3%" in text and "50,4%" in text
    assert "Часы переносим из темы «" in text
    assert any(t["tool"] == "get_hours_recommendation" for t in r["tool_calls"])
    _no_codes(text)
    # the hours equal the plan the planner computes for the same data
    plan = client.get(f"/api/v1/analyses/{r['analysis_ids'][0]}", headers=H).json()["result"]["scenarios"][0]
    t3 = next(c for c in plan["changes"] if c["title"].startswith("Сложение и вычитание дробей"))
    assert int(m.group(1)) == t3["delta"]


def test_best_textbook_question_has_no_single_winner(client, H, datasets):
    ds = datasets["base"]["id"]
    text = ask(client, H, ds, "Какой учебник лучше?")["output"]["text"]
    assert text.startswith("Единого лучшего пособия нет.")
    assert "Пособие Б сильнее в теме «Сложение и вычитание дробей" in text and "пособие А — в теме «Проценты»" in text
    assert "5,2 п.п." in text and "4,9 п.п." in text
    _no_codes(text)


def test_why_not_one_book_for_all_topics(client, H, datasets):
    ds = datasets["base"]["id"]
    text = ask(client, H, ds, "Почему нельзя просто выбрать пособие Б для всех тем?")["output"]["text"]
    assert text.startswith("Потому что преимущество зависит от темы")
    assert "«Проценты»" in text and "сильнее пособие А" in text
    _no_codes(text)


def test_kazakh_answers(client, H, datasets):
    ds = datasets["base"]["id"]
    h = ask(client, H, ds, "Бөлшектерді қосуға неше сағат қосу керек?", lang="kz")["output"]["text"]
    assert "сағат қосу ұсынылады" in h and "Бөлімдері әртүрлі бөлшектерді қосу және азайту" in h
    b = ask(client, H, ds, "Қай оқулық жақсы?", lang="kz")["output"]["text"]
    assert "бірыңғай үздік құрал жоқ" in b
    _no_codes(h)
    _no_codes(b)


class _MockProvider:
    """A provider that behaves like a live model: it calls the typed tools, then writes an answer."""

    name, model, config_error, data_policy, available, is_recorded = "mock", "mock-1", None, "api_default", True, False

    def __init__(self, answer):
        self.answer = answer

    def run_tools(self, system, user, tools, execute, max_steps=4):
        from types import SimpleNamespace

        assert "get_hours_recommendation" in {t.name for t in tools} and "compare_all_topics" in {t.name for t in tools}
        r = execute("get_hours_recommendation", {"topic": "сложение дробей"})
        execute("compare_all_topics", {})
        trace = [{"tool": "get_hours_recommendation", "input": {}, "ok": True}]
        return self.answer(r), trace, SimpleNamespace(model="mock-1", tokens=10)


def _live(monkeypatch, answer):
    from oqumap.ai import assistant, gate

    monkeypatch.setattr(assistant, "get_provider", lambda: _MockProvider(answer))
    monkeypatch.setattr(gate, "live_block_reason", lambda provider, synthetic=True: None)


def test_live_answer_codes_are_replaced_with_names(client, H, datasets, monkeypatch):
    _live(monkeypatch, lambda r: f"Добавьте {r['delta']} ч на T3 ({r['before']} → {r['after']}); в теме T3 сильнее EDB.")
    out = ask(client, H, datasets["base"]["id"], "Сколько часов добавить на дроби?")
    assert out["mode"] == "live_model"
    text = out["output"]["text"]
    assert "«Сложение и вычитание дробей с разными знаменателями»" in text and "Пособие Б" in text
    _no_codes(text)


def test_live_answer_with_invented_number_or_enum_falls_back(client, H, datasets, monkeypatch):
    _live(monkeypatch, lambda r: "Добавьте 7 ч: эффект пособия 31,4 п.п.")
    out = ask(client, H, datasets["base"]["id"], "Сколько часов добавить на сложение дробей?")
    assert out["mode"] == "template" and out["fallback_reason"] == "numeric_check_failed"
    _live(monkeypatch, lambda r: f"Добавьте {r['delta']} ч; статус comparable, уровень adjusted_association.")
    out = ask(client, H, datasets["base"]["id"], "Сколько часов добавить на сложение дробей?")
    assert out["mode"] == "template" and out["fallback_reason"] == "internal_codes_in_text"
    _no_codes(out["output"]["text"])
