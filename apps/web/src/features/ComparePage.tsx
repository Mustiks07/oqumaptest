import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useComparison, useCurrentDataset, useCurriculum, useEditionSummary, useGenerate, useOverview } from "../api/hooks";
import type { ComparisonResult, EditionSummaryResult, Envelope, GenerationOut } from "../api/types";
import { useI18n } from "../i18n/I18n";
import type { DictKey } from "../i18n/dict";
import { filtersParam, useAppState } from "../state/AppState";
import { Alert, Badge, Button, Card, Diff, Disclosure, ErrorState, Field, Loading, ModeBadge, ReasonList, Select, StaleBanner, StatusBadge } from "../ui";
import { GroupedBars } from "../ui/charts";
import { num, pct, pp } from "../ui/format";
import { editionName, useLabels, type EditionLike } from "../ui/labels";
import { FilterBar } from "./Filters";
import { NeedDataset } from "./OverviewPage";

export function ComparePage() {
  const { t, lang, pick } = useI18n();
  const st = useAppState();
  const nav = useNavigate();
  const cur = useCurriculum();
  const L = useLabels();
  const { dataset } = useCurrentDataset();
  const cmp = useComparison();
  const [scheme, setScheme] = useState("pre_three_level");
  const [weights, setWeights] = useState("pooled");
  const eds = cur.data?.editions ?? [];
  const summary = useEditionSummary(st.editionA, st.editionB, scheme, weights);
  const sEds = summary.data?.result.editions;
  const a = st.editionA ?? sEds?.a.id ?? eds[0]?.id ?? null;
  const b = st.editionB ?? sEds?.b.id ?? eds[1]?.id ?? null;
  const ov = useOverview();
  // default: the most difficult measured topic (first priority of the overview), not the first topic of the programme
  const firstPriority = (ov.data?.result.priorities[0] as { topic_id?: string } | undefined)?.topic_id;
  const topic: string | null = st.topicId ?? firstPriority ?? cur.data?.topics[0]?.id ?? null;

  const run = () => {
    if (!st.datasetId || !topic || !a || !b) return;
    cmp.mutate({ dataset_id: st.datasetId, topic_id: topic, edition_a_id: a, edition_b_id: b, filters: st.filters, strata_scheme: scheme, weight_mode: weights, include_topic_table: false },
      { onSuccess: () => st.markStep("compare") });
  };
  useEffect(() => {
    if (dataset?.code === "illustration") {
      setScheme("pre_two_level");
      setWeights("equal");
    }
  }, [dataset?.code]);
  useEffect(run, // eslint-disable-line react-hooks/exhaustive-deps
    [st.datasetId, topic, a, b, scheme, weights, filtersParam(st.filters), dataset?.version]);
  useEffect(() => {
    if (summary.data) st.updateDraft({ summaryAnalysisId: summary.data.context.analysis_id });
  }, [summary.data?.context.analysis_id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!st.datasetId) return <NeedDataset />;
  const env = cmp.data as Envelope<ComparisonResult> | undefined;
  const topicName = L.topic(topic);
  return (
    <div className="page stack">
      <div className="page-header">
        <div>
          <h1>{t("compare.title")}</h1>
          <p className="muted">{t("compare.lead")}</p>
        </div>
        <Button variant="primary" onClick={() => nav("/planner")}>{t("topic.to_plan")}</Button>
      </div>
      <FilterBar compact />
      {summary.isLoading && <Loading label={t("compare.summary_loading")} />}
      {summary.isError && <ErrorState error={summary.error} onRetry={() => summary.refetch()} />}
      {summary.data && <SummaryView res={summary.data.result} selected={topic} onSelect={(id) => st.setTopicId(id)} />}
      <Card title={t("compare.detail_title", { topic: topicName })} actions={
        <Select ariaLabel={t("compare.topic")} value={topic ?? ""} onChange={(v) => st.setTopicId(v)}
          options={(cur.data?.topics ?? []).map((x) => ({ value: x.id, label: pick(x, "title") }))} />
      }>
        {eds.length > 2 && (
          <div className="filters">
            <Field label={t("compare.edition_a")}>
              {(id) => <Select id={id} value={a ?? ""} onChange={(v) => st.setEditions(v, b)} options={eds.map((e) => ({ value: e.id, label: editionName(e, lang) }))} />}
            </Field>
            <Field label={t("compare.edition_b")}>
              {(id) => <Select id={id} value={b ?? ""} onChange={(v) => st.setEditions(a, v)} options={eds.map((e) => ({ value: e.id, label: editionName(e, lang) }))} />}
            </Field>
          </div>
        )}
        {cmp.isPending && <Loading />}
        {cmp.isError && <ErrorState error={cmp.error} onRetry={run} />}
        {env && !cmp.isPending && <ComparisonView env={env} />}
      </Card>
      <Disclosure summary={t("common.tech")}>
        <div className="filters">
          <Field label={t("compare.strata")}>
            {(id) => <Select id={id} value={scheme} onChange={setScheme} options={["pre_three_level", "pre_two_level"].map((v) => ({ value: v, label: t(`compare.strata.${v}` as DictKey) }))} />}
          </Field>
          <Field label={t("compare.weights")}>
            {(id) => <Select id={id} value={weights} onChange={setWeights} options={["pooled", "equal", "arm_a", "arm_b"].map((v) => ({ value: v, label: t(`compare.weights.${v}` as DictKey) }))} />}
          </Field>
        </div>
      </Disclosure>
      <Illustration />
    </div>
  );

  function ComparisonView({ env }: { env: Envelope<ComparisonResult> }) {
    const r = env.result;
    const na = editionName(r.editions.a as EditionLike, lang);
    const nb = editionName(r.editions.b as EditionLike, lang);
    const raw = r.raw as { a: { mean: number | null; n_learners: number; n_classes: number; n_schools: number; n_teachers: number }; b: { mean: number | null; n_learners: number; n_classes: number; n_schools: number; n_teachers: number }; difference: number | null };
    const adj = r.adjusted as { a: number | null; b: number | null; difference: number | null; unavailable_reason: string | null; weights: Record<string, number | null>; strata: { stratum: string; weight: number | null; n_a: number; mean_a: number | null; n_b: number; mean_b: number | null }[] };
    const unc = r.uncertainty as { cluster_unit: string; clusters_per_arm: { a: number; b: number }; adjusted_difference_ci: { low: number; high: number } | null; raw_difference_ci: { low: number; high: number } | null; unavailable_reason: string | null; replicates: number };
    const flip = raw.difference !== null && adj.difference !== null && Math.sign(raw.difference) !== Math.sign(adj.difference);
    const inDraft = st.draft.comparisonAnalysisId === env.context.analysis_id;
    const signalKey = `compare.signal.${r.signal}` as DictKey;
    return (
      <div className="stack">
        <StaleBanner ctx={env.context} onRecompute={run} />
        <div className="row">
          <StatusBadge status={r.status} labelKey={`comparability.${r.status}` as DictKey} />
          <Badge tone={r.inference_level === "adjusted_association" ? "info" : "neutral"}>{t(`inference.${r.inference_level}` as DictKey)}</Badge>
        </div>
        {r.status === "not_comparable" && <Alert tone="danger" title={t("compare.not_comparable")}>{t("compare.not_comparable_body")}</Alert>}
        <div className="grid grid-2">
          <GroupedBars
            title={`${t("compare.raw")} / ${t("compare.adjusted")}`}
            series={[t("compare.raw"), t("compare.adjusted")]}
            data={[
              { label: na, values: [{ series: t("compare.raw"), value: raw.a.mean, n: raw.a.n_learners }, { series: t("compare.adjusted"), value: adj.a }] },
              { label: nb, values: [{ series: t("compare.raw"), value: raw.b.mean, n: raw.b.n_learners }, { series: t("compare.adjusted"), value: adj.b }] },
            ]}
          />
          <div className="stack">
            <div className="table-wrap" tabIndex={0}>
              <table className="table" data-testid="comparison-table">
                <thead><tr><th /><th className="num">{na}</th><th className="num">{nb}</th><th className="num">{t("compare.difference", { a: na, b: nb })}</th></tr></thead>
                <tbody>
                  <tr><td>{t("compare.raw")}</td><td className="num">{pct(raw.a.mean, lang)}</td><td className="num">{pct(raw.b.mean, lang)}</td><td className="num"><Diff value={raw.difference} /></td></tr>
                  <tr><td>{t("compare.adjusted")}</td><td className="num">{pct(adj.a, lang)}</td><td className="num">{pct(adj.b, lang)}</td><td className="num" data-testid="adjusted-diff"><Diff value={adj.difference} /></td></tr>
                  <tr><td>{t("common.ci95")}</td><td /><td /><td className="num small">{unc.adjusted_difference_ci ? `${pp(unc.adjusted_difference_ci.low, lang)} … ${pp(unc.adjusted_difference_ci.high, lang)}` : <span className="muted">{t("common.ci_unavailable")}</span>}</td></tr>
                  <tr><td>{t("common.learners")} / {t("common.classes")} / {t("common.schools")}</td><td className="num small">{raw.a.n_learners} / {raw.a.n_classes} / {raw.a.n_schools}</td><td className="num small">{raw.b.n_learners} / {raw.b.n_classes} / {raw.b.n_schools}</td><td /></tr>
                </tbody>
              </table>
            </div>
            <p className="small">{t(signalKey, { a: na, b: nb })}</p>
            {flip && <Alert tone="warn">{t("compare.flip")}</Alert>}
            <p className="xs muted">{t("compare.cluster_note", { unit: t(`compare.cluster.${unc.cluster_unit}` as DictKey), na: unc.clusters_per_arm.a, nb: unc.clusters_per_arm.b })}</p>
            <div className="row">
              <Button variant={inDraft ? "primary" : "default"} aria-pressed={inDraft} data-testid="use-comparison" onClick={() => st.updateDraft({ comparisonAnalysisId: env.context.analysis_id })}>
                {inDraft ? `✓ ${t("compare.used")}` : t("compare.use_in_decision")}
              </Button>
            </div>
          </div>
        </div>
        <div className="grid grid-2">
          <div>
            <h3 className="small">{t("compare.strata_table")}</h3>
            <div className="table-wrap" tabIndex={0}>
              <table className="table">
                <thead><tr><th /><th className="num">{t("compare.weight")}</th><th className="num">{na}: n</th><th className="num">{na}</th><th className="num">{nb}: n</th><th className="num">{nb}</th></tr></thead>
                <tbody>
                  {adj.strata.map((s) => (
                    <tr key={s.stratum}>
                      <td>{t(`compare.${s.stratum}` as DictKey)}</td><td className="num">{pct(s.weight, lang, 0)}</td>
                      <td className="num">{num(s.n_a, lang)}</td><td className="num">{pct(s.mean_a, lang)}</td>
                      <td className="num">{num(s.n_b, lang)}</td><td className="num">{pct(s.mean_b, lang)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="xs muted" style={{ marginTop: 8 }}>{t("compare.strata_formula", { weights: t(`compare.weights.${weights}` as DictKey) })}</p>
          </div>
          <div>
            <h3 className="small">{t("compare.reasons")}</h3>
            {r.reasons.length ? <ReasonList reasons={r.reasons} /> : <Alert tone="ok">{t("comparability.comparable")}</Alert>}
            <Disclosure summary={t("common.tech")}>
              <p className="xs muted mono">{t("compare.forms")}: {(r.forms.a ?? []).join(", ")} / {(r.forms.b ?? []).join(", ")} · bootstrap ×{unc.replicates} · {env.context.method_version}</p>
            </Disclosure>
          </div>
        </div>
        <Explain analysisId={env.context.analysis_id} />
      </div>
    );
  }
}

function SummaryView({ res, selected, onSelect }: { res: EditionSummaryResult; selected: string | null; onSelect: (topicId: string) => void }) {
  const { t, lang, pick } = useI18n();
  const v = res.verdict;
  const na = editionName(res.editions.a, lang);
  const nb = editionName(res.editions.b, lang);
  const story = lang === "kz" ? v.raw_story_kz : v.raw_story_ru;
  return (
    <Card title={t("compare.verdict")} className="verdict-card">
      <p className="verdict-text" data-testid="edition-verdict">{lang === "kz" ? v.text_kz : v.text_ru}</p>
      {story && <Alert tone="warn" title={t("compare.raw_story")}><span data-testid="raw-story">{story}</span></Alert>}
      <div className="table-wrap" tabIndex={0} style={{ marginTop: 12 }}>
        <table className="table edition-matrix" data-testid="edition-matrix">
          <thead><tr>
            <th>{t("compare.col.topic")}</th><th>{t("compare.col.stronger")}</th><th className="num">{t("compare.col.diff")}</th>
            <th className="num">{t("compare.col.ci")}</th><th>{t("compare.col.evidence")}</th><th className="num">{t("compare.col.n", { a: na.replace(/^(Пособие|Учебник)\s+/, ""), b: nb.replace(/^(Пособие|Учебник)\s+/, "") })}</th>
          </tr></thead>
          <tbody>
            {res.rows.map((row) => {
              const comparable = row.status !== "not_comparable" && row.adjusted_difference != null;
              const lead = row.adjusted_difference == null ? null : row.adjusted_difference > 0 ? nb : na;
              const ci = row.ci;
              const adv = (x: number) => (row.adjusted_difference ?? 0) > 0 ? x : -x;
              return (
                <tr key={row.topic_id} className={`${row.topic_id === selected ? "selected " : ""}${row.confirmed ? "confirmed" : ""}`}
                  data-testid={`matrix-row-${row.code}`} onClick={() => onSelect(row.topic_id)} style={{ cursor: "pointer" }}>
                  <td><button type="button" className="link-button" onClick={() => onSelect(row.topic_id)}>{pick(row, "title")}</button></td>
                  <td>{!comparable ? <span className="muted">—</span> : row.confirmed ? <strong>{lead}</strong> : <span className="muted">{t("compare.no_leader")}</span>}</td>
                  <td className="num">{comparable && lead ? `${lead}: ${pp(Math.abs(row.adjusted_difference!), lang)}` : "—"}</td>
                  <td className="num small">{ci && comparable ? `${pp(Math.min(adv(ci.low), adv(ci.high)), lang)} … ${pp(Math.max(adv(ci.low), adv(ci.high)), lang)}` : "—"}</td>
                  <td>{!comparable ? <Badge tone="neutral">{t("compare.evidence.na")}</Badge> : row.confirmed ? <Badge tone="ok">{t("compare.evidence.yes")}</Badge> : <Badge tone="warn">{t("compare.evidence.no")}</Badge>}</td>
                  <td className="num small">{comparable ? `${num(row.n.a.learners, lang)} / ${num(row.n.b.learners, lang)}` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="xs muted" style={{ marginTop: 8 }}>{lang === "kz" ? v.detail_kz : v.detail_ru}</p>
      <p className="xs muted">{t("compare.pick_hint")}</p>
    </Card>
  );
}

function Explain({ analysisId }: { analysisId: string }) {
  const { t, lang } = useI18n();
  const gen = useGenerate<{ analysis_id: string; lang: string }>("/api/v1/ai/explain-comparison");
  const g = gen.data as GenerationOut | undefined;
  return (
    <Card title={t("compare.explain")} actions={<Button onClick={() => gen.mutate({ analysis_id: analysisId, lang })} disabled={gen.isPending} data-testid="explain-comparison">{t("compare.explain")}</Button>}>
      {gen.isPending && <Loading />}
      {gen.isError && <ErrorState error={gen.error} />}
      {g && (
        <div className="stack">
          <ModeBadge mode={g.mode} fallback={g.fallback_reason} />
          <div className="quote" data-testid="explanation-text">{String(g.output.text ?? "")}</div>
          {Array.isArray(g.output.limitations) && (
            <ul className="small">{(g.output.limitations as string[]).map((x, i) => <li key={i}>{x}</li>)}</ul>
          )}
          <div className="row"><Badge tone={(g.verification as { numbers?: { status: string } }).numbers?.status === "passed" ? "ok" : "danger"}>
            {(g.verification as { numbers?: { status: string } }).numbers?.status === "passed" ? t("ai.verified") : t("ai.unverified")}
          </Badge></div>
        </div>
      )}
    </Card>
  );
}

function Illustration() {
  const { t, lang } = useI18n();
  const q = useQuery({
    queryKey: ["composition-fixture"],
    queryFn: () => api.get<{ fixture: { cells: { arm: string; stratum: string; passed: number; total: number }[] }; raw: { a: { mean: number }; b: { mean: number } }; adjusted: { a: number; b: number } }>("/api/v1/fixtures/composition"),
  });
  return (
    <Card title={t("compare.illustration")}>
      <Disclosure summary={t("common.details")}>
        {q.isLoading ? <Loading /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data && (
          <div className="stack">
            <div className="table-wrap" tabIndex={0}>
              <table className="table" data-testid="illustration-table">
                <thead><tr><th /><th className="num">A</th><th className="num">B</th></tr></thead>
                <tbody>
                  {["high", "low"].map((s) => {
                    const ca = q.data.fixture.cells.find((c) => c.arm === "A" && c.stratum === s)!;
                    const cb = q.data.fixture.cells.find((c) => c.arm === "B" && c.stratum === s)!;
                    return (
                      <tr key={s}>
                        <td>{t(`compare.${s}` as DictKey)}</td>
                        <td className="num">{ca.passed} / {ca.total} ({pct(ca.passed / ca.total, lang, 0)})</td>
                        <td className="num">{cb.passed} / {cb.total} ({pct(cb.passed / cb.total, lang, 0)})</td>
                      </tr>
                    );
                  })}
                  <tr><td><strong>{t("compare.overall")}</strong></td><td className="num"><strong>{pct(q.data.raw.a.mean, lang, 0)}</strong></td><td className="num"><strong>{pct(q.data.raw.b.mean, lang, 0)}</strong></td></tr>
                  <tr><td><strong>{t("compare.equal_weights")}</strong></td><td className="num"><strong>{pct(q.data.adjusted.a, lang, 0)}</strong></td><td className="num"><strong>{pct(q.data.adjusted.b, lang, 0)}</strong></td></tr>
                </tbody>
              </table>
            </div>
            <p className="xs muted">{t("compare.illustration_note")}</p>
          </div>
        )}
      </Disclosure>
    </Card>
  );
}
