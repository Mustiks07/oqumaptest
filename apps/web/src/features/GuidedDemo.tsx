import { NavLink } from "react-router-dom";
import { useI18n } from "../i18n/I18n";
import type { DictKey } from "../i18n/dict";
import { GUIDE_STEPS, useAppState } from "../state/AppState";
import { Button } from "../ui";

const LINKS: Record<string, string> = {
  overview: "/overview", topic: "/topic", compare: "/compare", plan: "/planner", decision: "/decisions",
  approve: "/decisions", followup: "/decisions",
};

/** 7-step guided demo. Progress is stored locally (survives reloads); limitations stay visible. */
export function GuidedDemo() {
  const { t } = useI18n();
  const { progress, resetProgress } = useAppState();
  const done = GUIDE_STEPS.filter((s) => progress[s]).length;
  return (
    <details className="guide-compact" data-testid="guide">
      <summary>
        <span>
          <strong id="guide-title">{t("guide.title")}</strong>
          <span className="xs muted">{done}/{GUIDE_STEPS.length}</span>
        </span>
        <span className="bar-track" role="progressbar" aria-label={t("guide.title")} aria-valuemin={0} aria-valuemax={GUIDE_STEPS.length} aria-valuenow={done}>
          <span className="bar-fill" style={{ width: `${(100 * done) / GUIDE_STEPS.length}%` }} />
        </span>
      </summary>
      <div className="guide-content" aria-labelledby="guide-title">
        <ol className="stack xs">
          {GUIDE_STEPS.map((s) => (
            <li key={s}>
              <NavLink to={LINKS[s]} data-testid={`guide-${s}`} data-done={progress[s] ? "1" : "0"}>
                <span aria-hidden="true" className="guide-status">{progress[s] ? "✓" : "○"}</span>
                <span className={progress[s] ? "muted" : ""}>{t(`guide.step.${s}` as DictKey)}</span>
                {progress[s] && <span className="sr-only"> — выполнено</span>}
              </NavLink>
            </li>
          ))}
        </ol>
        <p className="xs muted">{t("guide.limits")}</p>
        {done > 0 && <Button size="sm" variant="ghost" onClick={resetProgress}>{t("guide.reset")}</Button>}
      </div>
    </details>
  );
}
