/** Application-wide analysis context: one dataset + one set of filters flows through every page, the assistant
 *  and the decision/report. Persisted in localStorage so a language switch or reload keeps it. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Filters, UserOut } from "../api/types";

export const DEFAULT_FILTERS: Filters = {
  school_ids: [],
  cohort_ids: [],
  edition_ids: [],
  language: null,
  outcome_stage: "post",
  attempt_rule: "first",
  omitted_policy: "as_incorrect",
  aggregation: "learner",
  mapping_status: "confirmed_only",
};

export interface DecisionDraftForm {
  target_group: string;
  problem: string;
  hypothesis: string;
  action: string;
  responsible: string;
  follow_up_date: string;
  follow_up_criterion: string;
}

/** Everything collected for a decision. Persisted (schema v2) so a reload (F5) keeps the analyses and the text. */
export interface DecisionDraftRefs {
  /** organisation the analysis IDs belong to: a different organisation (e.g. a new demo copy) invalidates them */
  orgId?: string;
  topicAnalysisId?: string;
  comparisonAnalysisId?: string;
  summaryAnalysisId?: string;
  planAnalysisId?: string;
  planPreset?: string;
  generationId?: string;
  sourceIds: string[];
  form?: DecisionDraftForm;
}

export interface AppStateValue {
  user: UserOut | null;
  setUser: (u: UserOut | null) => void;
  datasetId: string | null;
  setDatasetId: (id: string | null) => void;
  filters: Filters;
  setFilters: (f: Filters) => void;
  topicId: string | null;
  setTopicId: (id: string | null) => void;
  editionA: string | null;
  editionB: string | null;
  setEditions: (a: string | null, b: string | null) => void;
  draft: DecisionDraftRefs;
  updateDraft: (patch: Partial<DecisionDraftRefs>) => void;
  resetDraft: () => void;
  assistantOpen: boolean;
  setAssistantOpen: (v: boolean) => void;
  /** guided demo progress (per browser, survives reloads) */
  progress: Record<string, boolean>;
  markStep: (id: GuideStep) => void;
  resetProgress: () => void;
}

export const GUIDE_STEPS = ["overview", "topic", "compare", "plan", "decision", "approve", "followup"] as const;
export type GuideStep = (typeof GUIDE_STEPS)[number];

const Ctx = createContext<AppStateValue | null>(null);
const KEY = "oqumap.state.v2";
const LEGACY_KEYS = ["oqumap.state.v1"];
export const DRAFT_SCHEMA_VERSION = 2;

interface Persisted {
  datasetId: string | null;
  filters: Filters;
  topicId: string | null;
  editionA: string | null;
  editionB: string | null;
  draft: DecisionDraftRefs;
  progress: Record<string, boolean>;
}

function load(): Partial<Persisted> {
  try {
    const raw = localStorage.getItem(KEY) ?? LEGACY_KEYS.map((k) => localStorage.getItem(k)).find(Boolean) ?? null;
    const parsed = raw ? (JSON.parse(raw) as Partial<Persisted> & { schema?: number }) : {};
    // v1 → v2: same fields; the draft simply had no form / organisation yet
    if (parsed.draft && !Array.isArray(parsed.draft.sourceIds)) parsed.draft = { sourceIds: [] };
    return parsed;
  } catch {
    return {};
  }
}

export function AppStateProvider({ children }: { children: ReactNode }) {
  const saved = useMemo(load, []);
  const [user, setUser] = useState<UserOut | null>(null);
  const [datasetId, setDatasetIdState] = useState<string | null>(saved.datasetId ?? null);
  const [filters, setFilters] = useState<Filters>({ ...DEFAULT_FILTERS, ...(saved.filters ?? {}) });
  const [topicId, setTopicId] = useState<string | null>(saved.topicId ?? null);
  const [editionA, setA] = useState<string | null>(saved.editionA ?? null);
  const [editionB, setB] = useState<string | null>(saved.editionB ?? null);
  const [draft, setDraft] = useState<DecisionDraftRefs>(saved.draft ?? { sourceIds: [] });
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [progress, setProgress] = useState<Record<string, boolean>>(saved.progress ?? {});

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ schema: DRAFT_SCHEMA_VERSION, datasetId, filters, topicId, editionA, editionB, draft, progress }));
    } catch {
      /* ignore */
    }
  }, [datasetId, filters, topicId, editionA, editionB, draft, progress]);

  useEffect(() => {
    if (user?.org_id && draft.orgId && draft.orgId !== user.org_id) setDraft({ sourceIds: [] });
  }, [user?.org_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const setDatasetId = useCallback((id: string | null) => {
    setDatasetIdState((prev) => {
      if (prev !== id) {
        // a different dataset invalidates every collected reference
        setFilters(DEFAULT_FILTERS);
        setTopicId(null);
        setDraft({ sourceIds: [] });
      }
      return id;
    });
  }, []);

  const value: AppStateValue = {
    user,
    setUser,
    datasetId,
    setDatasetId,
    filters,
    setFilters,
    topicId,
    setTopicId,
    editionA,
    editionB,
    setEditions: (a, b) => {
      setA(a);
      setB(b);
    },
    draft,
    updateDraft: (patch) => setDraft((d) => ({ ...d, ...patch, orgId: user?.org_id ?? d.orgId })),
    resetDraft: () => setDraft({ sourceIds: [] }),
    assistantOpen,
    setAssistantOpen,
    progress,
    markStep: (id) => setProgress((p) => (p[id] ? p : { ...p, [id]: true })),
    resetProgress: () => setProgress({}),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState(): AppStateValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("AppStateProvider missing");
  return v;
}

export function filtersParam(f: Filters): string {
  return JSON.stringify(f);
}
