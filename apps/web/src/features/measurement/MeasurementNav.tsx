/** Second navigation group for the measurement & learning-loop screens (rendered by Layout). */
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useMeasurementReadiness } from "../../api/hooks";
import { useAppState } from "../../state/AppState";
import { useMT } from "./i18n";

const LINKS = [
  { to: "/quality", key: "nav.quality" },
  { to: "/interventions", key: "nav.interventions" },
  { to: "/pilots/new", key: "nav.pilot_new" },
  { to: "/portfolio/interventions", key: "nav.portfolio" },
] as const;

export function MeasurementNav() {
  const { t2 } = useMT();
  const { user } = useAppState();
  const readiness = useMeasurementReadiness(!!user?.org_is_ephemeral);
  const waiting = user?.org_is_ephemeral && readiness.data?.status !== "ready";
  const { pathname } = useLocation();
  const active = MEASUREMENT_ROUTES.some((route) => pathname.startsWith(route.split("/:")[0]));
  const [open, setOpen] = useState(active);
  useEffect(() => {
    if (active) setOpen(true);
  }, [active]);
  return (
    <section className="nav-group" data-testid="measurement-nav">
      <button type="button" className="nav-group-toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span id="m-nav-title">{t2("nav.group")}</span>
        <span aria-hidden="true" className="nav-chevron">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="nav-group-content">
          {waiting ? (
            <p className="xs muted" data-testid="measurement-nav-readiness">
              {readiness.data?.status === "failed" ? t2("nav.failed") : t2("nav.preparing")}
            </p>
          ) : (
            <ul aria-labelledby="m-nav-title" className="nav-list">
              {LINKS.map((l) => (
                <li key={l.to}>
                  <NavLink to={l.to} end={l.to === "/pilots/new"} className={({ isActive }) => (isActive ? "active" : "")}>{t2(l.key)}</NavLink>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

export const MEASUREMENT_ROUTES = [
  "/quality", "/quality/:assessmentId", "/interventions", "/interventions/:id", "/pilots/new", "/pilots/:id", "/pilots/:id/fidelity",
  "/pilots/:id/follow-up", "/portfolio/interventions",
] as const;
