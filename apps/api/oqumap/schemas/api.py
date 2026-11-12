"""Response contracts (exported to OpenAPI → packages/contracts/openapi.json → frontend TypeScript types).

Shares are 0..1; percentages exist only in the UI. Missing values are ``null`` with a separate reason field.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Model(BaseModel):
    model_config = ConfigDict(extra="allow")


class ErrorBody(Model):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(Model):
    error: ErrorBody
    request_id: str | None = None


class UserOut(Model):
    id: str
    username: str
    display_name: str
    roles: list[str]
    org_id: str
    org_name: str
    org_is_demo: bool
    org_is_ephemeral: bool = False
    org_expires_at: str | None = None


class LoginResponse(Model):
    token: str
    user: UserOut
    recommended_dataset_id: str | None = None


class DatasetSummary(Model):
    id: str
    code: str
    name_ru: str
    name_kz: str
    description_ru: str
    description_kz: str
    is_synthetic: bool
    scenario: str | None
    data_level: str
    version: int
    version_updated_at: str
    program_version_id: str | None
    manifest: dict[str, Any]


class AnalysisContext(Model):
    analysis_id: str
    dataset_id: str
    dataset_version: int
    current_dataset_version: int
    is_stale: bool
    is_synthetic: bool
    filters: dict[str, Any]
    method_version: str
    code_version: str
    computed_at: str
    kind: Literal["overview", "topic_evidence", "comparison", "edition_summary", "plan", "follow_up"]


class Envelope(Model, Generic[T]):
    context: AnalysisContext
    result: T


class MeanSummary(Model):
    mean: float | None
    ci_low: float | None
    ci_high: float | None
    ci_method: str | None
    ci_unavailable_reason: str | None
    n_learners: int
    n_classes: int
    n_schools: int
    aggregation: str


class TopicOverviewRow(Model):
    topic_id: str
    code: str
    title_ru: str
    title_kz: str
    status: str
    status_reason: str | None
    score: MeanSummary | None
    band: str | None
    n_items: int
    n_items_proposed_only: int
    objectives_total: int
    objectives_measured: int
    coverage: float | None
    deficit: float | None
    suppressed: bool = False
    suppression_reason: str | None = None


class HeatCohort(Model):
    cohort_id: str
    code: str
    school_code: str
    edition_code: str | None


class HeatCell(Model):
    topic_id: str
    cohort_id: str
    mean: float
    n: int


class Heatmap(Model):
    cohorts: list[HeatCohort]
    cells: list[HeatCell]


class OverviewResult(Model):
    outcome_assessments: list[dict[str, Any]]
    topics: list[TopicOverviewRow]
    priorities: list[dict[str, Any]]
    coverage_gaps: list[dict[str, Any]]
    heatmap: Heatmap
    counts: dict[str, int]
    bands: dict[str, float]
    rules: dict[str, str]


class OptionStat(Model):
    key: str
    text: str
    correct: bool
    misconception: str | None
    count: int | None
    share: float | None


class ItemEvidence(Model):
    item_id: str
    code: str
    stem_ru: str
    stem_kz: str
    objectives: list[dict[str, Any]]
    topic_weight: float
    n_answered: int | None
    n_omitted: int | None
    p_correct: float | None
    omit_rate: float | None
    options: list[OptionStat]


class ObjectiveEvidence(Model):
    objective_id: str
    code: str
    text_ru: str
    text_kz: str
    n_items_confirmed: int
    n_items_proposed: int
    status: str
    status_reason: str | None
    score: MeanSummary | None


class Misconception(Model):
    code: str
    label_ru: str
    label_kz: str
    diagnostic_check_ru: str
    n_learners: int | None
    share_of_learners: float | None
    eligible_learners: int | None = None
    selection_numerator: int | None = None
    opportunity_denominator: int | None = None
    opportunity_share: float | None = None
    items: list[str]
    interpretation: str
    method: str = "repeated_selection_v2"
    method_note_ru: str | None = None
    method_note_kz: str | None = None


class SourceRef(Model):
    link_id: str
    source_id: str
    objective_code: str
    status: str
    origin: str
    role: str
    edition_code: str | None
    edition_title: str | None
    page_physical: int | None
    page_printed: str | None
    anchor: str
    document_version: int
    excerpt: str


class TopicEvidenceResult(Model):
    topic: dict[str, Any]
    status: str
    summary: MeanSummary | None
    band: str | None
    objectives: list[ObjectiveEvidence]
    items: list[ItemEvidence]
    misconceptions: list[Misconception]
    classes: list[dict[str, Any]]
    prerequisites: list[dict[str, Any]]
    sources: list[SourceRef]
    exclusions: dict[str, int | None]
    rules: dict[str, str]
    outcome_assessments: list[str]
    suppressed: bool = False
    suppression_reason: str | None = None


class Reason(Model):
    code: str
    severity: Literal["info", "warn", "fail"]
    params: dict[str, Any]
    message_ru: str
    message_kz: str


class ArmRaw(Model):
    mean: float | None
    n_learners: int
    n_classes: int
    n_schools: int
    n_teachers: int


class StratumRow(Model):
    stratum: str
    weight: float | None
    n_a: int
    mean_a: float | None
    n_b: int
    mean_b: float | None


class ComparisonResult(Model):
    method_version: str
    status: Literal["comparable", "limited", "not_comparable"]
    reasons: list[Reason]
    inference_level: Literal["descriptive", "adjusted_association", "causal_protocol"]
    causal_protocol_available: bool
    ranking_allowed: bool
    signal: str
    raw: dict[str, Any]
    adjusted: dict[str, Any]
    uncertainty: dict[str, Any]
    baseline_coverage: float | None
    exclusions: dict[str, Any]
    topic: dict[str, Any]
    editions: dict[str, Any]
    forms: dict[str, list[str]]
    topic_table: dict[str, Any] | None = None


class EditionSummaryEdition(Model):
    id: str
    code: str
    title: str
    name_ru: str
    name_kz: str


class EditionSummaryRow(Model):
    topic_id: str
    code: str
    title_ru: str
    title_kz: str
    status: Literal["comparable", "limited", "not_comparable"]
    status_label_ru: str
    status_label_kz: str
    raw_a: float | None
    raw_b: float | None
    raw_difference: float | None
    adjusted_a: float | None
    adjusted_b: float | None
    adjusted_difference: float | None
    ci: dict[str, float] | None
    ci_unavailable_reason: str | None
    signal: str
    favoured: Literal["a", "b"] | None
    confirmed: bool
    n: dict[str, dict[str, int]]
    reasons: list[Reason]


class EditionVerdict(Model):
    kind: Literal["topic_dependent", "a_ahead", "b_ahead", "no_confirmed_difference", "insufficient"]
    a_topics: list[str]
    b_topics: list[str]
    unclear_topics: list[str]
    not_compared_topics: list[str]
    raw_a_ahead_topics: list[str]
    raw_b_ahead_topics: list[str]
    raw_misleading: bool
    text_ru: str
    text_kz: str
    detail_ru: str
    detail_kz: str
    raw_story_ru: str | None
    raw_story_kz: str | None


class EditionSummaryResult(Model):
    method_version: str
    comparison_method_version: str
    editions: dict[str, EditionSummaryEdition]
    rows: list[EditionSummaryRow]
    verdict: EditionVerdict
    exploratory: bool
    strata_scheme: str
    weight_mode: str


class PlanChange(Model):
    topic_id: str
    code: str
    title: str
    before: int
    after: int
    delta: int
    priority: float
    reason_kind: Literal["investment", "donor", "protected", "unchanged"]
    reason_ru: str
    reason_kz: str
    donor_reason_ru: str | None = None
    donor_reason_kz: str | None = None
    evidence: dict[str, Any]


class PlanScenario(Model):
    preset: str
    status: Literal["optimal", "feasible", "infeasible", "unknown", "invalid"]
    status_message_ru: str | None = None
    status_message_kz: str | None = None
    verdict_ru: str | None = None
    verdict_kz: str | None = None
    human_status: Literal["ready", "needs_attention"] | None = None
    hours: dict[str, int] | None
    validation: dict[str, Any] | None
    conflict: dict[str, Any] | None
    changes: list[PlanChange] | None = None
    total_before: int | None = None
    total_after: int | None = None
    objective_value: float | None = None
    objective: dict[str, Any] | None = None
    solver: dict[str, Any] | None = None
    technical_details: dict[str, Any] | None = None
    input_errors: list[dict[str, Any]] | None = None


class PlanResult(Model):
    scenarios: list[PlanScenario]
    budget: int
    is_calendar: bool
    input: dict[str, Any]
    source_analysis_id: str | None
    note_ru: str


class JobOut(Model):
    id: str
    kind: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: float
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    attempts: int
    created_at: str
    started_at: str | None
    finished_at: str | None


class ImportBatchOut(Model):
    id: str
    filename: str
    kind: str
    status: str
    file_sha256: str
    transform_version: str
    rows_total: int
    rows_accepted: int
    rows_rejected: int
    created_at: str
    committed_at: str | None
    resulting_dataset_version: int | None
    is_synthetic: bool
    dataset_id: str | None
    sheet: str | None = None
    column_mapping: dict[str, str] | None = None
    report: dict[str, Any] | None = None


class GenerationOut(Model):
    generation_id: str
    task: str
    mode: Literal["live_model", "recorded_demo", "template"]
    mode_label: str
    provider: str
    model: str | None
    prompt_template_version: str
    created_at: str
    output: dict[str, Any]
    citations: list[str]
    verification: dict[str, Any]
    review_status: str
    fallback_reason: str | None


class AssistantAnswer(GenerationOut):
    analysis_ids: list[str]
    tool_calls: list[dict[str, Any]]
    sources: list[dict[str, Any]]


class DecisionOut(Model):
    id: str
    decision_group_id: str
    version: int
    status: Literal["draft", "approved", "superseded"]
    dataset_id: str
    dataset_version: int
    current_dataset_version: int
    is_stale: bool
    filters: dict[str, Any]
    target_group: str
    topic_id: str | None
    problem: str
    hypothesis: str
    action: str
    responsible: str
    follow_up_date: str | None
    follow_up_criterion: str
    analysis_ids: list[str]
    plan_analysis_id: str | None
    snapshot: dict[str, Any]
    created_at: str
    created_by: str | None
    approved_by: str | None
    approved_at: str | None
    approval_note: str | None
    outcome_status: str | None
    history: list[dict[str, Any]]
    follow_ups: list[dict[str, Any]]
    is_synthetic: bool


class FollowUpResponse(Envelope[dict[str, Any]]):
    decision: DecisionOut


class SourceOut(Model):
    source_id: str
    document_id: str
    document_filename: str
    document_version: int
    document_sha256: str
    media_type: str
    is_demo: bool
    edition: dict[str, Any] | None
    anchor: str
    page_physical: int | None
    page_printed: str | None
    heading: str | None
    text: str
    text_sha256: str
    context: list[dict[str, Any]]
