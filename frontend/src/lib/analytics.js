// Derive dashboard metrics from the pipeline state. Pure functions, no UI.

export const KNOWLEDGE_AREAS = [
  "Integration", "Scope", "Schedule", "Cost", "Quality",
  "Resources", "Communications", "Risk", "Procurement", "Stakeholders",
];

const LEVELS = ["low", "medium", "high"];

export function level(text, fallback = "medium") {
  const s = String(text || "").toLowerCase();
  if (/\bhigh\b|\bsevere\b|\bcritical\b|\bvery likely\b|\blikely\b/.test(s)) return "high";
  if (/\blow\b|\bminor\b|\bunlikely\b|\brare\b/.test(s)) return "low";
  if (/\bmedium\b|\bmoderate\b|\bpossible\b/.test(s)) return "medium";
  return fallback;
}

// KA -> compliance score (0..100); undefined where not scored
export function kaScores(state) {
  const out = {};
  (state?.validation_report?.section_scores || []).forEach((s) => {
    out[s.knowledge_area] = s.score;
  });
  return out;
}

export function radarData(state) {
  const m = kaScores(state);
  return KNOWLEDGE_AREAS.map((ka) => ({ ka, score: m[ka] ?? 0,
    short: ka.slice(0, 4) }));
}

export function findingCounts(state) {
  const f = state?.validation_report?.findings || [];
  return {
    alignment: f.filter((x) => x.finding_type === "alignment").length,
    gap: f.filter((x) => x.finding_type === "gap").length,
    risk_flag: f.filter((x) => x.finding_type === "risk_flag").length,
  };
}

export function riskItems(state) {
  return state?.risk_gap_list?.items || [];
}

// 3x3 likelihood (rows, high->low) x impact (cols, low->high) count grid
export function riskMatrix(state) {
  const grid = {};
  LEVELS.forEach((l) => LEVELS.forEach((i) => (grid[`${l}|${i}`] = 0)));
  riskItems(state).forEach((it) => {
    const l = level(it.likelihood || it.severity);
    const i = level(it.impact || it.severity);
    grid[`${l}|${i}`] += 1;
  });
  return grid;
}

export function severityDist(items) {
  const d = { high: 0, medium: 0, low: 0 };
  items.forEach((it) => { d[level(it.severity)] = (d[level(it.severity)] || 0) + 1; });
  return d;
}

export function kaConcentration(items) {
  const d = {};
  items.forEach((it) => {
    const k = it.knowledge_area || "—";
    d[k] = (d[k] || 0) + 1;
  });
  return d;
}

export function priorityDist(state) {
  const d = { high: 0, medium: 0, low: 0 };
  (state?.recommendations?.items || []).forEach((r) => {
    d[level(r.priority)] = (d[level(r.priority)] || 0) + 1;
  });
  return d;
}

export function planCoverage(state) {
  const present = new Set((state?.draft_plan?.sections || [])
    .map((s) => s.knowledge_area));
  return KNOWLEDGE_AREAS.map((ka) => ({ ka, covered: present.has(ka) }));
}

// Composite "Project Readiness Index" (0..100): compliance, risk pressure,
// and recommendation coverage of weak areas.
export function readinessIndex(state) {
  const compliance = state?.optimized_plan?.compliance_score
    ?? state?.validation_report?.overall_compliance_score ?? 0;
  const items = riskItems(state);
  const sev = severityDist(items);
  // risk pressure: weighted high/med/low, capped
  const pressure = Math.min(100, (sev.high * 18 + sev.medium * 8 + sev.low * 3));
  const recs = (state?.recommendations?.items || []).length;
  const recCoverage = Math.min(100, recs * 9);
  const idx = 0.6 * compliance + 0.25 * (100 - pressure) + 0.15 * recCoverage;
  return Math.max(0, Math.min(100, Math.round(idx)));
}

export function readinessVerdict(idx, highGaps) {
  if (idx >= 78) return { label: "Ready to proceed", tone: "ok" };
  if (idx >= 58) return {
    label: highGaps > 0 ? `Conditionally ready — address ${highGaps} high-severity item(s)`
      : "Conditionally ready", tone: "warn" };
  return { label: "Not ready — significant gaps/risks", tone: "bad" };
}

export function weakestAreas(state, n = 3) {
  return Object.entries(kaScores(state))
    .sort((a, b) => a[1] - b[1]).slice(0, n)
    .map(([ka, score]) => ({ ka, score }));
}
