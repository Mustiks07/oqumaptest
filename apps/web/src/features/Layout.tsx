import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, setToken } from "../api/client";
import { useCurrentDataset } from "../api/hooks";
import { useI18n } from "../i18n/I18n";
import type { DictKey } from "../i18n/dict";
import { useAppState } from "../state/AppState";
import { Button } from "../ui";
import { Assistant } from "./Assistant";
import { GuidedDemo } from "./GuidedDemo";
import { MeasurementNav } from "./measurement/MeasurementNav";

const STEPS: { to: string; key: DictKey }[] = [
  { to: "/datasets", key: "nav.datasets" },
  { to: "/overview", key: "nav.overview" },
  { to: "/topic", key: "nav.topic" },
  { to: "/compare", key: "nav.compare" },
  { to: "/materials", key: "nav.materials" },
  { to: "/planner", key: "nav.planner" },
  { to: "/decisions", key: "nav.decision" },
];

const TOOLS: { to: string; key: DictKey; icon: string; testId?: string }[] = [
  { to: "/graph", key: "graph.title", icon: "◇", testId: "nav-graph" },
  { to: "/sandbox", key: "sandbox.title", icon: "⇄" },
  { to: "/calendar", key: "calendar.title", icon: "▦", testId: "nav-calendar" },
  { to: "/quizzes", key: "quiz.title", icon: "?" },
  { to: "/data-quality", key: "quality.title", icon: "i" },
  { to: "/import", key: "datasets.own_data", icon: "↑", testId: "nav-import" },
];

function NavGroup({ title, testId, paths, children }: { title: string; testId: string; paths: string[]; children: ReactNode }) {
  const { pathname } = useLocation();
  const active = paths.some((path) => pathname === path || pathname.startsWith(`${path}/`));
  const [open, setOpen] = useState(active);
  useEffect(() => {
    if (active) setOpen(true);
  }, [active]);
  return (
    <section className="nav-group" data-testid={testId}>
      <button type="button" className="nav-group-toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span>{title}</span>
        <span aria-hidden="true" className="nav-chevron">{open ? "−" : "+"}</span>
      </button>
      {open && <div className="nav-group-content">{children}</div>}
    </section>
  );
}

export function Layout() {
  const { t, lang, setLang } = useI18n();
  const { user, setUser, assistantOpen, setAssistantOpen } = useAppState();
  const { dataset } = useCurrentDataset();
  const nav = useNavigate();
  const qc = useQueryClient();
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <a className="brand" href="/datasets" onClick={(e) => { e.preventDefault(); nav("/datasets"); }}>
            OquMap
          </a>
          <span>{lang === "kz" ? "Оқу картасы" : "Карта обучения"}</span>
        </div>
        {dataset ? (
          <span className="row small header-context" style={{ gap: 8, flexWrap: "nowrap", minWidth: 0, flex: "0 1 auto", overflow: "hidden" }} data-testid="dataset-chip">
            <span className="muted">{t("header.dataset")}:</span>
            <strong style={{ maxWidth: 320, minWidth: 40, flexShrink: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={lang === "kz" ? dataset.name_kz : dataset.name_ru}>
              {lang === "kz" ? dataset.name_kz : dataset.name_ru}
            </strong>
          </span>
        ) : null}
        <span className="header-spacer" />
        <div className="row" role="group" aria-label={t("header.lang")} style={{ gap: 4 }}>
          {(["ru", "kz"] as const).map((l) => (
            <Button key={l} size="sm" variant={lang === l ? "primary" : "default"} aria-pressed={lang === l} onClick={() => setLang(l)}>
              {l.toUpperCase()}
            </Button>
          ))}
        </div>
        <Button size="sm" onClick={() => setAssistantOpen(!assistantOpen)} aria-expanded={assistantOpen} disabled={!dataset}>
          {t("nav.assistant")}
        </Button>
        {user && (
          <span className="small muted" title={`${user.display_name} · ${user.org_name}`} style={{ whiteSpace: "nowrap", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis" }}>
            {user.display_name}
          </span>
        )}
        <Button size="sm" variant="ghost" onClick={() => { api.post("/api/v1/auth/logout").catch(() => undefined); setToken(null); setUser(null); qc.clear(); nav("/login"); }}>
          {t("header.logout")}
        </Button>
      </header>
      <nav className="app-nav" aria-label="Шаги сценария">
        <NavLink to="/demo-3min" className={({ isActive }) => `tour-link${isActive ? " active" : ""}`} data-testid="nav-tour">
          <span className="nav-step" aria-hidden="true">▶</span>
          {t("tour.title")}
        </NavLink>
        <p className="nav-eyebrow">{t("nav.methodist_path")}</p>
        <ol className="scenario-nav">
          {STEPS.map((s, i) => (
            <li key={s.to}>
              <NavLink to={s.to} className={({ isActive }) => (isActive ? "active" : "")}>
                <span className="nav-step" aria-hidden="true">{i + 1}</span>
                {t(s.key)}
              </NavLink>
            </li>
          ))}
        </ol>
        <NavGroup title={t("nav.tools")} testId="nav-tools-group" paths={TOOLS.map((item) => item.to)}>
          <ul className="nav-list">
            {TOOLS.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} className={({ isActive }) => (isActive ? "active" : "")} data-testid={item.testId}>
                  <span className="nav-step" aria-hidden="true">{item.icon}</span>
                  {t(item.key)}
                </NavLink>
              </li>
            ))}
            {user?.roles.includes("admin") && !user.org_is_demo && (
              <li>
                <NavLink to="/users" className={({ isActive }) => (isActive ? "active" : "")}>
                  <span className="nav-step" aria-hidden="true">⚙</span>
                  {t("nav.users")}
                </NavLink>
              </li>
            )}
          </ul>
        </NavGroup>
        {user?.org_is_demo && <GuidedDemo />}
        <MeasurementNav />
      </nav>
      <main className="app-main" id="main">
        <Outlet />
      </main>
      {assistantOpen && dataset && <Assistant onClose={() => setAssistantOpen(false)} />}
    </div>
  );
}
