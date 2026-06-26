import { motion } from "framer-motion";
import { Gauge, ShieldCheck, CircleDashed, TriangleAlert, Lightbulb, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ComplianceGauge, RadarKA, KAHeatmap, RiskMatrix, DistributionDonut, StatTile, Ring } from "@/components/Charts";
import {
  readinessIndex, readinessVerdict, kaScores, radarData, findingCounts,
  riskItems, riskMatrix, severityDist, weakestAreas, KNOWLEDGE_AREAS,
} from "@/lib/analytics";
import { cn } from "@/lib/utils";

const fade = {
  hidden: { opacity: 0, y: 14 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.05, duration: 0.4 } }),
};

function M({ i = 0, className, children }) {
  return (
    <motion.div variants={fade} custom={i} initial="hidden" animate="show" className={className}>
      {children}
    </motion.div>
  );
}

export function ExecutiveDashboard({ state }) {
  const compliance = state.optimized_plan?.compliance_score
    ?? state.validation_report?.overall_compliance_score ?? 0;
  const idx = readinessIndex(state);
  const items = riskItems(state);
  const sev = severityDist(items);
  const fc = findingCounts(state);
  const recs = state.recommendations?.items?.length || 0;
  const verdict = readinessVerdict(idx, sev.high);
  const scoresMap = kaScores(state);
  const heat = KNOWLEDGE_AREAS.map((ka) => ({ knowledge_area: ka, score: scoresMap[ka] ?? 0 }));
  const weak = weakestAreas(state);

  const verdictTone = { ok: "border-success/40 bg-success/10 text-success",
    warn: "border-warning/40 bg-warning/10 text-warning",
    bad: "border-destructive/40 bg-destructive/10 text-destructive" }[verdict.tone];

  const findingDonut = [
    { name: "Aligned", key: "alignment", value: fc.alignment },
    { name: "Gaps", key: "gap", value: fc.gap },
    { name: "Risk flags", key: "risk_flag", value: fc.risk_flag },
  ].filter((d) => d.value);

  return (
    <div className="space-y-5">
      <M i={0} className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-extrabold tracking-tight">
            <Sparkles className="h-5 w-5 text-primary" /> Executive Dashboard
          </h2>
          <p className="text-sm text-muted-foreground">Unified project scoring &amp; readiness across all PMO stages.</p>
        </div>
        <div className={cn("rounded-full border px-4 py-1.5 text-sm font-semibold", verdictTone)}>
          {verdict.label}
        </div>
      </M>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[
          { label: "Readiness Index", value: idx, sub: "composite 0-100", tone: verdict.tone === "ok" ? "ok" : verdict.tone === "bad" ? "bad" : "warn", icon: Gauge },
          { label: "Compliance", value: compliance, sub: "PMO score", tone: "brand", icon: ShieldCheck },
          { label: "Open Gaps", value: fc.gap, sub: "to address", tone: "warn", icon: CircleDashed },
          { label: "Risk Flags", value: fc.risk_flag + sev.high, sub: `${sev.high} high-severity`, tone: "bad", icon: TriangleAlert },
          { label: "Recommendations", value: recs, sub: "AI-generated", tone: "ok", icon: Lightbulb },
        ].map((k, i) => (
          <M key={k.label} i={i + 1}><StatTile {...k} /></M>
        ))}
      </div>

      {/* main analytics grid */}
      <div className="grid gap-5 lg:grid-cols-3">
        <M i={1}>
          <Card className="h-full">
            <CardHeader><CardTitle>Overall scoring</CardTitle></CardHeader>
            <CardContent className="flex flex-col items-center gap-4">
              <ComplianceGauge score={compliance} size={170} />
              <div className="flex gap-5">
                <Ring value={idx} label="readiness" />
                <Ring value={Math.max(0, 100 - Math.min(100, sev.high * 18 + sev.medium * 8 + sev.low * 3))} label="risk-free" />
              </div>
            </CardContent>
          </Card>
        </M>
        <M i={2}>
          <Card className="h-full">
            <CardHeader><CardTitle>Knowledge-area profile</CardTitle></CardHeader>
            <CardContent><RadarKA data={radarData(state)} /></CardContent>
          </Card>
        </M>
        <M i={3}>
          <Card className="h-full">
            <CardHeader><CardTitle>Risk exposure matrix</CardTitle></CardHeader>
            <CardContent>
              <RiskMatrix grid={riskMatrix(state)} />
              <div className="mt-3 border-t border-border pt-3">
                <DistributionDonut data={findingDonut} />
              </div>
            </CardContent>
          </Card>
        </M>
      </div>

      {/* KA compliance heatmap */}
      <M i={4}>
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Compliance heatmap — by knowledge area</CardTitle>
            <span className="text-xs text-muted-foreground">red &lt;55 · amber 55-74 · green ≥75</span>
          </CardHeader>
          <CardContent>
            <KAHeatmap scores={heat} />
            {weak.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
                <span className="text-muted-foreground">Focus areas:</span>
                {weak.map((w) => (
                  <span key={w.ka} className="rounded-md bg-destructive/15 px-2 py-0.5 text-xs font-semibold text-destructive">
                    {w.ka} ({w.score})
                  </span>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </M>
    </div>
  );
}
