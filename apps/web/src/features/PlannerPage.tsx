import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { usePlanContext, useSolve } from "../api/hooks";
import type { Envelope, PlanResult, PlanScenario, TopicInput } from "../api/types";
import { useI18n } from "../i18n/I18n";
import type { DictKey } from "../i18n/dict";
import { useAppState } from "../state/AppState";
import { Alert, Button, Card, Disclosure, ErrorState, Field, Loading, QueryView, StaleBanner, StatusBadge, Tabs } from "../ui";
import { HoursChart } from "../ui/charts";
import { pct } from "../ui/format";
import { NeedDataset } from "./OverviewPage";

type Row = TopicInput & {
  status?: string | null; score?: number | null; basis?: string; diag?: boolean;
  protected?: boolean; protectionReason?: string | null;
};
const PRESETS = ["balanced", "minimal_changes", "focus_problem_topics"];

export function PlannerPage() {
  const { t, lang, pick } = useI18n();
  const st = useAppState();
  const ctx = usePlanContext();
  const solve = useSolve();
  const [mode, setMode] = useState<"current" | "illustration">("current");
  const [rows, setRows] = useState<Row[]>([]);
  const [budget, setBudget] = useState(0);
  const [penalty, setPenalty] = useState(0.05);
  const [presets, setPresets] = useState<string[]>(["balanced", "minimal_changes", "focus_problem_topics"]);

  useEffect(() => {
    if (!ctx.data) return;
    if (mode === "current") {
      setRows(ctx.data.topics.map((tp) => ({
        topic_id: tp.topic_id, code: tp.code, title: pick(tp as unknown as Record<string, unknown>, "title"), current_hours: tp.current_hours,
        priority: tp.priority, min_hours: tp.min_hours, max_hours: tp.max_hours, fixed: false, elapsed_hours: tp.elapsed_hours,
        max_change: null, status: tp.topic_status, score: tp.score, basis: tp.priority_basis, diag: tp.recommend_diagnostic,
        protected: tp.protected_from_reduction, protectionReason: lang === "kz" ? tp.protection_reason_kz : tp.protection_reason_ru,
      })));
      setBudget(ctx.data.budget);
    } else {
      const il = ctx.data.illustration_20h;
      setRows(il.topics.map((x) => ({ topic_id: null, code: x.code, title: x.title, current_hours: x.current_hours, priority: x.priority,
        min_hours: x.min_hours ?? null, max_hours: x.max_hours ?? null, fixed: false, elapsed_hours: 0, max_change: null })));
      setBudget(il.budget);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ctx.data, mode, lang]);

  if (!st.datasetId) return <NeedDataset />;
  const upd = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const intOrNull = (v: string) => (v === "" ? null : Math.max(0, Math.round(Number(v))));
  const run = () =>
    solve.mutate({
      dataset_id: st.datasetId!, plan_id: mode === "current" ? ctx.data?.plan?.id ?? null : null, filters: st.filters,
      topics: rows.map(({ status: _s, score: _sc, basis: _b, diag: _d, protected: _p, protectionReason: _pr, ...r }) => r), budget, change_penalty: penalty,
      presets, time_limit_seconds: 5, source_analysis_id: ctx.data?.source_analysis_id ?? null,
    }, { onSuccess: () => { if (mode === "current") st.markStep("plan"); } });
  const env = solve.data as Envelope<PlanResult> | undefined;
  const sum = rows.reduce((a, r) => a + r.current_hours, 0);
  return (
    <div className="page stack">
      <div className="page-header">
        <div>
          <h1>{t("planner.title")}</h1>
          <p className="muted">{t("planner.lead")}</p>
        </div>
      </div>
      <Tabs label={t("planner.title")} active={mode} onChange={(m) => { setMode(m as "current" | "illustration"); solve.reset(); }}
        tabs={[{ id: "current", label: t("planner.load_current") }, { id: "illustration", label: t("planner.illustration") }]} />
      <QueryView q={ctx}>
        {(c) => (
          <Card title={mode === "current" ? (c.plan?.name ?? t("planner.load_current")).replace(/\s*\(условный\)$/i, "") : t("planner.illustration")}
            actions={<Button variant="primary" onClick={run} disabled={solve.isPending || presets.length === 0} data-testid="solve">{t("planner.solve")}</Button>}>
            <div className="grid grid-3" data-testid="planner-table" style={{ marginBottom: 12 }}>
              <div className="metric"><span className="metric-label">{t("planner.budget")}</span><span className="metric-value">{budget} {t("planner.hours_short")}</span></div>
              <div className="metric"><span className="metric-label">{t("planner.measured_topics")}</span><span className="metric-value">{rows.filter((r) => r.score != null).length}/{rows.length}</span></div>
              <div className="metric"><span className="metric-label">{t("planner.protected_topics")}</span><span className="metric-value">{rows.filter((r) => r.protected).length}</span></div>
            </div>
            <Alert tone="info">{t("planner.simple_hint")}</Alert>
            <Disclosure summary={t("planner.manual_settings")}>
            <div className="table-wrap" tabIndex={0}>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("planner.topic")}</th><th className="num">{t("planner.current")}</th><th className="num">{t("planner.elapsed")}</th>
                    <th className="num">{t("planner.min")}</th><th className="num">{t("planner.max")}</th><th className="num">{t("planner.max_change")}</th>
                    <th>{t("planner.fixed")}</th><th className="num">{t("planner.priority")}</th><th>{t("planner.priority_basis")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.code}>
                      <td><strong>{r.title}</strong>{r.diag && <div className="xs" style={{ color: "var(--color-warn)" }}>⚠ {t("planner.diagnostic")}</div>}{r.protected && <div className="xs" style={{ color: "var(--color-primary)" }}>◆ {r.protectionReason ?? t("planner.protected")}</div>}</td>
                      <td className="num"><input aria-label={`${r.code} ${t("planner.current")}`} className="input input-num" type="number" min={0} value={r.current_hours} onChange={(e) => upd(i, { current_hours: intOrNull(e.target.value) ?? 0 })} /></td>
                      <td className="num"><input aria-label={`${r.code} ${t("planner.elapsed")}`} className="input input-num" type="number" min={0} value={r.elapsed_hours ?? 0} onChange={(e) => upd(i, { elapsed_hours: intOrNull(e.target.value) ?? 0 })} /></td>
                      <td className="num"><input aria-label={`${r.code} ${t("planner.min")}`} className="input input-num" type="number" min={0} value={r.min_hours ?? ""} onChange={(e) => upd(i, { min_hours: intOrNull(e.target.value) })} data-testid={`min-${r.code}`} /></td>
                      <td className="num"><input aria-label={`${r.code} ${t("planner.max")}`} className="input input-num" type="number" min={0} value={r.max_hours ?? ""} onChange={(e) => upd(i, { max_hours: intOrNull(e.target.value) })} /></td>
                      <td className="num"><input aria-label={`${r.code} ${t("planner.max_change")}`} className="input input-num" type="number" min={0} value={r.max_change ?? ""} onChange={(e) => upd(i, { max_change: intOrNull(e.target.value) })} /></td>
                      <td><input aria-label={`${r.code} ${t("planner.fixed")}`} type="checkbox" checked={!!r.fixed} onChange={(e) => upd(i, { fixed: e.target.checked })} data-testid={`fixed-${r.code}`} /></td>
                      <td className="num"><input aria-label={`${r.code} ${t("planner.priority")}`} className="input input-num" type="number" min={0} step={0.05} value={r.priority ?? 0} onChange={(e) => upd(i, { priority: Math.max(0, Number(e.target.value)) })} /></td>
                      <td className="xs">{r.basis ? t(`planner.basis.${r.basis}` as DictKey) : "—"}{r.score != null ? ` · ${pct(r.score, lang)}` : ""}{r.status ? <> <StatusBadge status={r.status} /></> : null}</td>
                    </tr>
                  ))}
                  <tr><td><strong>{t("planner.total")}</strong></td><td className="num"><strong>{sum}</strong></td><td colSpan={7} /></tr>
                </tbody>
              </table>
            </div>
            <div className="filters" style={{ marginTop: 12 }}>
              <Field label={t("planner.budget")}>{(id) => <input id={id} className="input" type="number" min={0} value={budget} onChange={(e) => setBudget(Math.max(0, Math.round(Number(e.target.value))))} data-testid="budget" />}</Field>
              <Field label={t("planner.penalty")}>{(id) => <input id={id} className="input" type="number" min={0} step={0.01} value={penalty} onChange={(e) => setPenalty(Math.max(0, Number(e.target.value)))} />}</Field>
              <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
                <legend className="xs muted" style={{ fontWeight: 550 }}>{t("planner.presets")}</legend>
                {PRESETS.map((p) => (
                  <label key={p} className="checkbox" style={{ marginRight: 12 }}>
                    <input type="checkbox" checked={presets.includes(p)} onChange={(e) => setPresets((ps) => (e.target.checked ? [...ps, p] : ps.filter((x) => x !== p)))} />
                    {t(`planner.preset.${p}` as DictKey)}
                  </label>
                ))}
              </fieldset>
            </div>
            </Disclosure>
            <Disclosure summary={t("planner.how_priority")}>
              <p className="xs muted">{c.priority_rule} · {t("planner.weights_version")}: {c.weights_version}</p>
            </Disclosure>
          </Card>
        )}
      </QueryView>
      {solve.isPending && <Loading />}
      {solve.isError && <ErrorState error={solve.error} onRetry={run} />}
      {env && (
        <>
          <StaleBanner ctx={env.context} onRecompute={run} />
          <Alert tone="info">{env.result.note_ru}</Alert>
          <div className="grid grid-3" style={{ gridTemplateColumns: `repeat(${Math.min(3, env.result.scenarios.length)}, minmax(0,1fr))` }}>
            {env.result.scenarios.map((sc) => <ScenarioCard key={sc.preset} sc={sc} analysisId={env.context.analysis_id} canUse={mode === "current"} />)}
          </div>
        </>
      )}
    </div>
  );
}

function ScenarioCard({ sc, analysisId, canUse }: { sc: PlanScenario; analysisId: string; canUse: boolean }) {
  const { t, lang } = useI18n();
  const st = useAppState();
  const nav = useNavigate();
  const used = st.draft.planAnalysisId === analysisId && st.draft.planPreset === sc.preset;
  const verdict = (lang === "kz" ? sc.verdict_kz : sc.verdict_ru)
    ?? (lang === "kz" ? sc.status_message_kz : sc.status_message_ru)
    ?? t("planner.needs_attention");
  return (
    <Card title={t(`planner.preset.${sc.preset}` as DictKey)}>
      <div className="stack" data-testid={`scenario-${sc.preset}`}>
        <Alert tone={sc.human_status === "ready" ? "ok" : "warn"}>
          <strong>{verdict}</strong>
        </Alert>
        {sc.changes && (
          <>
            <HoursChart title={t("planner.result")} labels={[t("planner.before"), t("planner.after")]} rows={sc.changes.map((ch) => ({ code: ch.title, before: ch.before, after: ch.after }))} />
            <div className="plan-change-list">
              {sc.changes.filter((change) => change.delta !== 0).map((change) => (
                <article className="plan-change" key={change.code}>
                  <div className="plan-change-head">
                    <strong>{change.title}</strong>
                    <span className={`plan-delta ${change.delta > 0 ? "diff-pos" : "diff-neg"}`}>{change.before} → {change.after} ч ({change.delta > 0 ? `+${change.delta}` : `−${Math.abs(change.delta)}`})</span>
                  </div>
                  <p>{lang === "kz" ? change.reason_kz : change.reason_ru}</p>
                  {change.delta < 0 && (() => {
                    const donorReason = lang === "kz" ? change.donor_reason_kz : change.donor_reason_ru;
                    const reason = lang === "kz" ? change.reason_kz : change.reason_ru;
                    return donorReason && donorReason.trim() !== reason.trim()
                      ? <p className="xs muted"><strong>{t("planner.why_donor")}:</strong> {donorReason}</p>
                      : null;
                  })()}
                </article>
              ))}
            </div>
            {sc.validation?.valid && <Alert tone="ok">{t("planner.valid")}</Alert>}
            <Disclosure summary={t("planner.how_calculated")}>
              <div className="stack xs muted">
                <span>{t("planner.technical_status")}: {sc.status}</span>
                <span>{lang === "kz" ? sc.status_message_kz : sc.status_message_ru}</span>
                <span>{t("planner.objective")}: {String(sc.objective?.formula ?? "")}; λ={String(sc.objective?.change_penalty ?? "")}, r={String(sc.objective?.diminishing_rate ?? "")}</span>
                <span>{t("planner.time")}: {String((sc.solver as { wall_time_seconds?: number })?.wall_time_seconds ?? "")} s</span>
              </div>
            </Disclosure>
            {canUse && (
              <div className="row">
                <Button variant={used ? "primary" : "default"} aria-pressed={used} data-testid={`use-plan-${sc.preset}`} onClick={() => st.updateDraft({ planAnalysisId: analysisId, planPreset: sc.preset })}>
                  {used ? `✓ ${t("compare.used")}` : t("planner.use_in_decision")}
                </Button>
                {used && <Button variant="primary" onClick={() => nav("/decisions")}>{t("planner.go_decision")}</Button>}
              </div>
            )}
          </>
        )}
        {sc.status === "infeasible" && sc.conflict && (
          <div className="stack" data-testid="conflict">
            <strong>{t("planner.conflict")}</strong>
            <span className="small">{t("planner.conflict_lead")}</span>
            <ul className="small">
              {(sc.conflict.constraints as { key: string; message_ru: string; message_kz: string }[]).map((c) => <li key={c.key}>{lang === "kz" ? c.message_kz : c.message_ru}</li>)}
            </ul>
            {(sc.conflict.arithmetic as { sum_lower_bounds: number; budget: number } | null) && (
              <Alert tone="danger">{t("planner.arithmetic", { lower: (sc.conflict.arithmetic as { sum_lower_bounds: number }).sum_lower_bounds, budget: (sc.conflict.arithmetic as { budget: number }).budget })}</Alert>
            )}
            <span className="xs muted">verified: {String(sc.conflict.verified)}</span>
          </div>
        )}
        {sc.status === "unknown" && <Alert tone="warn">{sc.status_message_ru}</Alert>}
        {sc.input_errors && <Alert tone="danger">{JSON.stringify(sc.input_errors)}</Alert>}
      </div>
    </Card>
  );
}
