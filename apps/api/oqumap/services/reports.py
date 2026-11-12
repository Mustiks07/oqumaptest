"""Decision report export. Everything is rendered from the decision snapshot (and recorded follow-ups), so
numbers, filters and versions match the analysis snapshot shown on screen.

* PDF: human-readable report (reportlab, embedded DejaVu font for Cyrillic/Kazakh).
* CSV / XLSX: tabular results; any cell starting with = + - @ tab or CR is prefixed with an apostrophe so no
  user text becomes an executable formula.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(v):
    if isinstance(v, str) and v.startswith(FORMULA_PREFIXES):
        return "'" + v
    return v


def pct(x, digits=1):
    return "—" if x is None else f"{100 * x:.{digits}f}%".replace(".", ",")


def pp(x, digits=1):
    return "—" if x is None else (f"{100 * x:+.{digits}f}".replace(".", ",") + " п.п.")


def rows_for_tables(dec: dict) -> list[list]:
    """Long table: section, metric, group, value, unit, note."""
    s = dec["snapshot"]
    rows: list[list] = [["section", "metric", "group", "value", "unit", "note"]]
    rows.append(["context", "decision_id", "", dec["id"], "", f"version {dec['version']} / {dec['status']}"])
    rows.append(["context", "dataset", "", s["dataset"]["name_ru"], "", f"version {s['dataset']['version']}"])
    rows.append(["context", "is_synthetic", "", str(s["dataset"]["is_synthetic"]).lower(), "", ""])
    for k, v in s["filters"].items():
        rows.append(["filters", k, "", ",".join(v) if isinstance(v, list) else ("" if v is None else str(v)), "", ""])
    for a in s["analyses"]:
        rows.append(["analysis", a["kind"], "", a["analysis_id"], "", f"dataset_version={a['dataset_version']}; method={a['method_version']}"])
    t = s.get("topic")
    if t:
        sm = t.get("summary") or {}
        rows.append(["topic", "mean_score_share", t["code"], sm.get("mean"), "share", t["status"]])
        rows.append(["topic", "ci_low", t["code"], sm.get("ci_low"), "share", sm.get("ci_method") or sm.get("ci_unavailable_reason")])
        rows.append(["topic", "ci_high", t["code"], sm.get("ci_high"), "share", ""])
        for k in ("n_learners", "n_classes", "n_schools"):
            rows.append(["topic", k, t["code"], sm.get(k), "count", ""])
        for o in t["objectives"]:
            rows.append(["objective", "mean_score_share", o["code"], o["mean"], "share", o["status"]])
        for it in t["items"]:
            rows.append(["item", "p_correct", it["code"], it["p_correct"], "share", f"answered={it['n_answered']}; omitted={it['n_omitted']}"])
        for mc in t["misconceptions"]:
            rows.append(["misconception", "share_of_learners", mc["code"], mc["share_of_learners"], "share", mc["label_ru"]])
        for k, v in t["exclusions"].items():
            rows.append(["exclusions", k, t["code"], v, "count", ""])
    c = s.get("comparison")
    if c:
        ea, eb = c["editions"]["a"]["code"], c["editions"]["b"]["code"]
        rows.append(["comparison", "status", "", c["status"], "", c["inference_level"]])
        rows.append(["comparison", "raw_mean", ea, c["raw"]["a"]["mean"], "share", f"n={c['raw']['a']['n_learners']}"])
        rows.append(["comparison", "raw_mean", eb, c["raw"]["b"]["mean"], "share", f"n={c['raw']['b']['n_learners']}"])
        rows.append(["comparison", "adjusted_mean", ea, c["adjusted"]["a"], "share", c["adjusted"]["weight_mode"]])
        rows.append(["comparison", "adjusted_mean", eb, c["adjusted"]["b"], "share", c["adjusted"]["weight_mode"]])
        rows.append(["comparison", "adjusted_difference_b_minus_a", "", c["adjusted"]["difference"], "share_points", ""])
        ci = c["uncertainty"]["adjusted_difference_ci"] or {}
        rows.append(["comparison", "ci_low", "", ci.get("low"), "share_points", c["uncertainty"].get("unavailable_reason") or c["uncertainty"]["cluster_unit"]])
        rows.append(["comparison", "ci_high", "", ci.get("high"), "share_points", ""])
        for st in c["adjusted"]["strata"]:
            rows.append(["stratum", "weight", st["stratum"], st["weight"], "share", ""])
            rows.append(["stratum", "mean", f"{st['stratum']}:{ea}", st["mean_a"], "share", f"n={st['n_a']}"])
            rows.append(["stratum", "mean", f"{st['stratum']}:{eb}", st["mean_b"], "share", f"n={st['n_b']}"])
        for r in c["reasons"]:
            rows.append(["comparison_reason", r["code"], r["severity"], "", "", r["message_ru"]])
    pl = s.get("plan")
    if pl:
        rows.append(["plan", "status", pl["preset"], pl["status"], "", ""])
        for ch in pl["changes"]:
            rows.append(["plan", "hours_before", ch["code"], ch["before"], "hours", ""])
            rows.append(["plan", "hours_after", ch["code"], ch["after"], "hours", f"delta={ch['delta']:+d}"])
        rows.append(["plan", "total", "", pl["total_after"], "hours", f"before={pl['total_before']}"])
    for src in s.get("sources", []):
        rows.append(["source", "citation", (src.get("edition") or {}).get("code", ""), src["source_id"], "",
                     f"{src['document_filename']} v{src['document_version']} {('p.' + src['page_printed']) if src['page_printed'] else src['anchor']}"])
    for fu in dec.get("follow_ups", []):
        r = fu["result"] or {}
        tg = r.get("target") or {}
        rows.append(["follow_up", "status", fu["id"], fu["status"], "", r.get("interpretation_level", "")])
        rows.append(["follow_up", "adjusted_change", "target", tg.get("adjusted_change"), "share_points", ""])
        if tg.get("ci"):
            rows.append(["follow_up", "ci_low", "target", tg["ci"]["low"], "share_points", ""])
            rows.append(["follow_up", "ci_high", "target", tg["ci"]["high"], "share_points", ""])
    for lim in s.get("limitations", []):
        rows.append(["limitation", "", "", "", "", lim])
    return rows


def to_csv(dec: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for row in rows_for_tables(dec):
        w.writerow([safe_cell("" if v is None else v) for v in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(dec: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    for i, row in enumerate(rows_for_tables(dec)):
        cells = []
        for v in row:
            v = safe_cell(v)
            cells.append(v)
        ws.append(cells)
        if i == 0:
            for c in ws[1]:
                c.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if isinstance(c.value, str):
                c.data_type = "s"  # force text type; never a formula
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 40
    ws.column_dimensions["F"].width = 80
    info = wb.create_sheet("about")
    info.append(["OquMap — экспорт решения"])
    info.append(["Синтетические данные" if dec["snapshot"]["dataset"]["is_synthetic"] else "Данные организации"])
    info.append(["Доли указаны от 0 до 1; разницы — в долях (×100 = п.п.)."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


T = {
    "title": ("Решение по теме «{topic}»", "«{topic}» тақырыбы бойынша шешім"),
    "title_plain": ("Методическое решение", "Әдістемелік шешім"),
    "status_line": ("Версия {v} · {status} · {date}", "{v}-нұсқа · {status} · {date}"),
    "synthetic": ("Демонстрационные данные: ученики, классы, школы и пособия вымышлены.",
                  "Демонстрациялық деректер: оқушылар, сыныптар, мектептер мен құралдар ойдан алынған."),
    "summary": ("Краткий вывод", "Қысқаша қорытынды"),
    "found": ("Что обнаружено", "Не анықталды"),
    "change": ("Что рекомендуем изменить", "Нені өзгертуді ұсынамыз"),
    "why": ("Почему именно это решение", "Неге дәл осы шешім"),
    "hours": ("Из каких тем перенесены часы", "Сағаттар қай тақырыптардан ауыстырылды"),
    "materials": ("Какие материалы использовать", "Қандай материалдарды пайдалану керек"),
    "check": ("Как и когда проверим результат", "Нәтижені қалай және қашан тексереміз"),
    "limits": ("Ограничения данных", "Деректердің шектеулері"),
    "appendix": ("Техническое приложение", "Техникалық қосымша"),
    "col_topic": ("Тема", "Тақырып"), "col_result": ("Средний результат", "Орташа нәтиже"),
    "col_ci": ("95% интервал", "95% интервал"), "col_n": ("Учеников / классов", "Оқушы / сынып"),
    "col_goal": ("Цель обучения", "Оқу мақсаты"), "col_error": ("Возможная ошибка (гипотеза)", "Ықтимал қате (гипотеза)"),
    "col_share": ("Доля учеников", "Оқушылар үлесі"), "col_before": ("Было, ч", "Болды, сағ"), "col_after": ("Стало, ч", "Болады, сағ"),
    "col_delta": ("Изменение", "Өзгеріс"), "col_reason": ("Почему", "Неге"), "col_book": ("Пособие", "Құрал"),
    "col_place": ("Место", "Орны"), "col_fragment": ("Фрагмент", "Үзінді"),
    "budget_same": ("Общий объём часов не меняется: {total} ч.", "Сағаттардың жалпы көлемі өзгермейді: {total} сағ."),
    "plan_checked": ("План проверен независимым валидатором ограничений.", "Жоспар шектеулердің тәуелсіз валидаторымен тексерілді."),
    "no_plan": ("План часов к решению не прикреплён.", "Шешімге сағат жоспары тіркелмеген."),
    "date": ("Дата повторной проверки", "Қайта тексеру күні"), "criterion": ("Критерий", "Өлшем"),
    "responsible": ("Ответственный", "Жауапты"), "target": ("Для кого", "Кімге"),
    "approved": ("Утверждено", "Бекітілді"), "followup": ("Повторная проверка", "Қайта тексеру"),
    "dynamics_note": ("наблюдаемая динамика, а не оценка воздействия", "бақыланатын динамика, әсерді бағалау емес"),
    "page": ("стр.", "бет"), "page_short": ("с.", "б."),
    "footer": ("OquMap · решение сформировано из сохранённых анализов", "OquMap · шешім сақталған талдаулардан жасалды"),
    "raw_vs_adj": ("Без поправки на входной уровень: {a} — {ra}, {b} — {rb}. С учётом входного уровня учеников: {a} — {aa}, {b} — {ab}",
                   "Кіріс деңгейін ескермегенде: {a} — {ra}, {b} — {rb}. Кіріс деңгейін ескергенде: {a} — {aa}, {b} — {ab}"),
    "lead": ("; {lead} впереди на {d} (95% интервал преимущества от {lo} до {hi}).", "; {lead} {d} алда (95% интервал: {lo} – {hi})."),
    "no_diff": ("; различие данными не подтверждается.", "; айырма расталмайды."),
    "flip": ("Направление различия изменилось после учёта входного уровня — сырой рейтинг здесь вводит в заблуждение.",
             "Кіріс деңгейін ескергенде айырма бағыты өзгерді — шикі рейтинг адастырады."),
    "status_draft": ("черновик", "жоба"), "status_approved": ("утверждено", "бекітілді"), "status_superseded": ("заменено", "ауыстырылды"),
    "appendix_note": ("Для проверки расчёта: версии данных и методов, правила подсчёта.", "Есептеуді тексеру үшін: деректер мен әдістер нұсқалары."),
    "rules": ("Правила подсчёта", "Есептеу ережелері"), "analyses": ("Сохранённые анализы", "Сақталған талдаулар"),
}
RULES_HUMAN = {
    "attempt_rule": {"first": ("первая попытка ученика", "оқушының бірінші әрекеті"), "last": ("последняя попытка ученика", "оқушының соңғы әрекеті")},
    "omitted_policy": {"as_incorrect": ("пропуск считается неверным ответом", "өткізіп алу қате жауап болып саналады"),
                       "exclude": ("пропуск исключается из расчёта", "өткізіп алу есептен шығарылады")},
    "aggregation": {"learner": ("среднее по ученикам", "оқушылар бойынша орташа"), "class": ("среднее по классам", "сыныптар бойынша орташа")},
    "mapping_status": {"confirmed_only": ("только подтверждённая разметка заданий", "тек расталған белгілеу"),
                       "include_proposed": ("включая предложенную разметку", "ұсынылған белгілеуді қоса")},
}


def _t(key: str, lang: str, **kw) -> str:
    ru, kz = T[key]
    return (kz if lang == "kz" else ru).format(**kw)


def _ppa(x, lang="ru") -> str:
    return "—" if x is None else f"{100 * abs(x):.1f}".replace(".", ",") + (" п.т." if lang == "kz" else " п.п.")


def _plural_ru(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    return forms[1] if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else forms[2]


def to_pdf(dec: dict, lang: str = "ru", appendix: bool = False) -> bytes:
    """Management document: conclusion first, then what was found, what changes, why, hours, materials, how it is
    checked and the limits. Internal codes, filter enums, solver formulas and IDs are kept out of the main part; they
    appear only in the optional technical appendix."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from .labels import edition_name

    lang = "kz" if lang == "kz" else "ru"
    li = 1 if lang == "kz" else 0
    try:
        pdfmetrics.getFont("OquSans")
    except KeyError:
        pdfmetrics.registerFont(TTFont("OquSans", str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("OquSans-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    s = dec["snapshot"]
    base = ParagraphStyle("base", fontName="OquSans", fontSize=9.5, leading=13, alignment=TA_LEFT, allowWidows=0, allowOrphans=0)
    small = ParagraphStyle("small", parent=base, fontSize=8.5, leading=11.5, textColor=colors.HexColor("#4a5568"))
    cell = ParagraphStyle("cell", parent=base, fontSize=8.5, leading=11)
    h1 = ParagraphStyle("h1", parent=base, fontName="OquSans-Bold", fontSize=17, leading=22, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=base, fontName="OquSans-Bold", fontSize=11.5, leading=15, spaceBefore=9, spaceAfter=4,
                        textColor=colors.HexColor("#1a365d"))
    lead_style = ParagraphStyle("lead", parent=base, fontSize=11, leading=15.5, backColor=colors.HexColor("#eef2ff"),
                                borderPadding=8, borderColor=colors.HexColor("#c3cdf5"), borderWidth=0.6)
    note = ParagraphStyle("note", parent=small, backColor=colors.HexColor("#fff7e6"), borderPadding=4, textColor=colors.HexColor("#7b341e"))

    def P(text, style=base):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)

    def table(data, widths, header=True):
        t = Table([[P(c, cell) if not isinstance(c, Paragraph) else c for c in row] for row in data], colWidths=widths,
                  repeatRows=1 if header else 0)
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e0")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2f7")))
        t.setStyle(TableStyle(style))
        return t

    def section(title_key, *flow):
        """Heading kept together with the start of its content (no orphan headings at the bottom of a page)."""
        flow = [f for f in flow if f is not None]
        if not flow:
            return []
        return [KeepTogether([P(_t(title_key, lang), h2), flow[0]]), *flow[1:]]

    topic = s.get("topic") or {}
    title = topic.get(f"title_{lang}") or topic.get("title_ru")
    rec = s.get("recommendation") or {}
    hours = rec.get("hours")
    material = rec.get("material") or {}
    plan = s.get("plan")
    comp = s.get("comparison")
    width = A4[0] - 36 * mm

    story = [P(_t("title", lang, topic=title) if title else _t("title_plain", lang), h1)]
    status = _t(f"status_{dec['status']}", lang) if f"status_{dec['status']}" in T else dec["status"]
    story.append(P(_t("status_line", lang, v=dec["version"], status=status, date=dec["created_at"][:10]), small))
    if s["dataset"]["is_synthetic"]:
        story += [Spacer(1, 3), P(_t("synthetic", lang), note)]
    story.append(Spacer(1, 8))

    # 1) short conclusion
    first_action = dec["action"].split(". ")[0].rstrip(".") + "."
    concl = [first_action]
    if material.get(f"why_{lang}"):
        concl.append(material[f"why_{lang}"])
    if dec.get("follow_up_date"):
        concl.append(f"{_t('date', lang)}: {dec['follow_up_date']}.")
    story.append(P(" ".join(concl), lead_style))

    # 2) what was found
    sm = topic.get("summary") or {}
    found = [P(dec["problem"])]
    if sm.get("mean") is not None:
        ci = f"{pct(sm.get('ci_low'))} – {pct(sm.get('ci_high'))}" if sm.get("ci_low") is not None else "—"
        found += [Spacer(1, 5), table([[_t("col_topic", lang), _t("col_result", lang), _t("col_ci", lang), _t("col_n", lang)],
                                       [title, pct(sm.get("mean")), ci, f"{sm.get('n_learners')} / {sm.get('n_classes')}"]],
                                      [width * 0.43, width * 0.19, width * 0.2, width * 0.18])]
    objs = [o for o in topic.get("objectives", []) if o.get("mean") is not None]
    if objs:
        found += [Spacer(1, 5), table([[_t("col_goal", lang), _t("col_result", lang)]] +
                                      [[o.get(f"text_{lang}") or o["text_ru"], pct(o["mean"])] for o in sorted(objs, key=lambda o: o["mean"])],
                                      [width * 0.78, width * 0.22])]
    mcs = topic.get("misconceptions") or []
    if mcs:
        found += [Spacer(1, 5), table([[_t("col_error", lang), _t("col_share", lang)]] +
                                      [[mc.get(f"label_{lang}") or mc["label_ru"], pct(mc["share_of_learners"])] for mc in mcs],
                                      [width * 0.78, width * 0.22])]
    story += section("found", *found)

    # 3) what changes (the full action text; the conclusion above is its first sentence)
    story += section("change", P(dec["action"]))

    # 4) why
    why = [P(dec["hypothesis"])]  # the reason for the hours themselves is in the hours table below
    if comp and comp["adjusted"].get("difference") is not None:
        ea, eb = comp["editions"]["a"], comp["editions"]["b"]
        na = ea.get(f"name_{lang}") or edition_name(ea.get("title"), ea["code"], lang)
        nb = eb.get(f"name_{lang}") or edition_name(eb.get("title"), eb["code"], lang)
        d = comp["adjusted"]["difference"]
        ci = comp["uncertainty"].get("adjusted_difference_ci")
        txt = _t("raw_vs_adj", lang, a=na, b=nb, ra=pct(comp["raw"]["a"]["mean"]), rb=pct(comp["raw"]["b"]["mean"]),
                 aa=pct(comp["adjusted"]["a"]), ab=pct(comp["adjusted"]["b"]))
        if ci and (ci["low"] > 0 or ci["high"] < 0):
            lo, hi = (ci["low"], ci["high"]) if d > 0 else (-ci["high"], -ci["low"])
            txt += _t("lead", lang, lead=nb if d > 0 else na, d=_ppa(d, lang), lo=_ppa(lo, lang), hi=_ppa(hi, lang))
        else:
            txt += _t("no_diff", lang)
        why += [Spacer(1, 4), P(txt)]
        rd = comp["raw"].get("difference")
        if rd is not None and rd * d < 0:
            why.append(P(_t("flip", lang), small))
    es = s.get("edition_summary")
    if es and es.get(f"text_{lang}"):
        why += [Spacer(1, 4), P(es[f"text_{lang}"])]
    story += section("why", *why)

    # 5) hours
    if plan:
        changed = [ch for ch in plan["changes"] if ch["delta"]]
        rows = [[_t("col_topic", lang), _t("col_before", lang), _t("col_after", lang), _t("col_delta", lang), _t("col_reason", lang)]]
        for ch in changed:
            name = ch.get(f"title_{lang}") or ch["title"]
            reason = ch.get(f"reason_{lang}") or ch.get("reason_ru") or ""
            rows.append([name, ch["before"], ch["after"], f"{ch['delta']:+d} ч".replace("-", "−") if lang == "ru"
                         else f"{ch['delta']:+d} сағ".replace("-", "−"), reason])
        flow = [table(rows, [width * 0.23, width * 0.1, width * 0.1, width * 0.12, width * 0.45])] if changed else []
        if plan.get("total_before") == plan.get("total_after"):
            flow.append(P(_t("budget_same", lang, total=plan["total_after"]) + " " + (_t("plan_checked", lang) if plan["validation"]["valid"] else ""), small))
        story += section("hours", *flow)
    else:
        story += section("hours", P(_t("no_plan", lang), small))

    # 6) materials
    srcs = s.get("sources") or []
    if srcs:
        rows = [[_t("col_book", lang), _t("col_place", lang), _t("col_fragment", lang)]]
        for src in srcs:
            ed = src.get("edition") or {}
            book = edition_name(ed.get("title"), ed.get("code"), lang) if ed else src["document_filename"]
            place = f"{_t('page_short', lang)} {src['page_printed']}" if src.get("page_printed") else (src.get("heading") or "—")
            rows.append([book, place, src["text"][:320]])
        story += section("materials", table(rows, [width * 0.17, width * 0.22, width * 0.61]),
                         P(material[f"why_{lang}"], small) if material.get(f"why_{lang}") else None)

    # 7) follow-up
    check_rows = [[_t("date", lang), dec.get("follow_up_date") or "—"],
                  [_t("criterion", lang), dec.get("follow_up_criterion") or "—"],
                  [_t("responsible", lang), dec.get("responsible") or "—"],
                  [_t("target", lang), dec.get("target_group") or "—"]]
    if dec.get("approved_at"):
        check_rows.append([_t("approved", lang), f"{dec.get('approved_by') or ''} · {dec['approved_at'][:10]}"])
    flow = [table(check_rows, [width * 0.3, width * 0.7], header=False)]
    for fu in dec.get("follow_ups") or []:
        r = fu["result"] or {}
        tg = r.get("target") or {}
        change = tg.get("adjusted_change")
        flow.append(P(f"{_t('followup', lang)}: {fu.get('status_label_' + lang) or fu['status_label_ru']}; "
                      f"{pct((tg.get('before') or {}).get('adjusted'))} → {pct((tg.get('after') or {}).get('adjusted'))}"
                      + (f" ({pp(change)})" if change is not None else "") + f" — {_t('dynamics_note', lang)}.", base))
    story += section("check", *flow)

    # 8) limits (human sentences only), kept in one block so it never leaves a lonely line on a new page
    lims = [x for x in dict.fromkeys(s.get("limitations_kz" if lang == "kz" and s.get("limitations_kz") else "limitations", [])) if x]
    if lims:
        story.append(KeepTogether([P(_t("limits", lang), h2), *[P("• " + x, small) for x in lims]]))

    if appendix:
        story += [PageBreak(), P(_t("appendix", lang), h2), P(_t("appendix_note", lang), small), Spacer(1, 4)]
        f = s.get("filters") or {}
        rules = [RULES_HUMAN[k].get(f.get(k), (str(f.get(k)),) * 2)[li] for k in RULES_HUMAN if k in f]
        story += [P(_t("rules", lang) + ": " + "; ".join(rules) + ".", small)]
        story += [P(_t("analyses", lang) + ": " + "; ".join(f"{a['kind']} {a['analysis_id'][:8]} · v{a['dataset_version']} · "
                                                             f"{a['method_version']}" for a in s.get("analyses", [])), small)]
        if plan and plan.get("objective"):
            story.append(P(f"planner: {plan['objective'].get('formula', '')}; λ={plan['objective'].get('change_penalty')}", small))
        if comp:
            story.append(P(f"comparison: {comp['adjusted'].get('strata_scheme')} / {comp['adjusted'].get('weight_mode')} · "
                           f"bootstrap {comp['uncertainty'].get('replicates')} · {comp['uncertainty'].get('cluster_unit')}", small))

    def on_page(canvas, doc):
        canvas.setFont("OquSans", 7.5)
        canvas.setFillColor(colors.HexColor("#718096"))
        canvas.drawString(18 * mm, 10 * mm, _t("footer", lang))
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{_t('page', lang)} {doc.page}")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=_t("title", lang, topic=title) if title else _t("title_plain", lang), author="OquMap")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def _status_ru(s):
    return {"draft": "черновик", "approved": "утверждено", "superseded": "заменено новой версией"}.get(s, s)


def _objective_status(s):
    return {"measured": "измерено", "unverified_mapping": "разметка не подтверждена", "not_measured": "не измерялось"}.get(s, s)


def _filters_text(f: dict) -> str:
    parts = [f"попытка: {f['attempt_rule']}", f"пропуск: {f['omitted_policy']}", f"агрегация: {f['aggregation']}",
             f"разметка: {f['mapping_status']}", f"этап: {f['outcome_stage']}"]
    for k in ("school_ids", "cohort_ids", "edition_ids"):
        if f.get(k):
            parts.append(f"{k}: {len(f[k])}")
    if f.get("language"):
        parts.append(f"язык: {f['language']}")
    return "; ".join(parts)
