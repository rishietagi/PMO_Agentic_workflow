import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CategoryBar, BreakdownPie } from "@/components/Charts";
import { getDashboard } from "@/lib/api";

function Metric({ value, label }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="text-3xl font-extrabold tracking-tight">{value}</div>
        <div className="mt-1 text-xs text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  );
}

export function Dashboard({ refreshKey }) {
  const [agg, setAgg] = React.useState(null);
  React.useEffect(() => { getDashboard().then(setAgg).catch(() => {}); }, [refreshKey]);
  if (!agg) return <div className="text-sm text-muted-foreground">Loading…</div>;

  const gapAreas = (agg.most_common_gap_areas || []).map(([name, value]) => ({ name, value }));
  const gapVsRisk = Object.entries(agg.gap_vs_risk || {}).map(([k, v]) => ({
    name: k === "gap" ? "Gaps" : "Risks", key: k, value: v,
  }));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Feedback dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Flow steps 7–8: instrumentation only — no auto-retraining (Phase 2).
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Metric value={agg.n_feedback} label="Runs rated" />
        <Metric value={agg.avg_rating ?? "—"} label="Avg rating" />
        <Metric value={agg.pct_helpful != null ? agg.pct_helpful + "%" : "—"} label="% helpful" />
        <Metric value={agg.n_runs} label="Pipeline runs" />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Most-flagged gap / risk areas</CardTitle></CardHeader>
          <CardContent><CategoryBar data={gapAreas} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Gap vs. risk split</CardTitle></CardHeader>
          <CardContent><BreakdownPie data={gapVsRisk} /></CardContent>
        </Card>
      </div>

      {agg.recent_comments?.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Recent comments</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {agg.recent_comments.map((c, i) => (
              <div key={i} className="rounded-lg border border-border bg-card/60 px-3 py-2 text-sm text-muted-foreground">{c}</div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
