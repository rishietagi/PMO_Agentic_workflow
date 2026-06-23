import * as React from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FindingCard, Citations } from "@/components/FindingCard";
import { ComplianceGauge, SectionScoresChart, BreakdownPie } from "@/components/Charts";
import { FeedbackForm } from "@/components/FeedbackForm";
import { sevRank } from "@/lib/utils";
import { TriangleAlert, CircleDashed, CheckCircle2, Lightbulb, Sparkles } from "lucide-react";

function List({ title, items }) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{title}</div>
      {items && items.length ? (
        <ul className="space-y-1.5 text-sm leading-relaxed">{items.map((x, i) => <li key={i}>• {x}</li>)}</ul>
      ) : (
        <div className="text-sm italic text-muted-foreground">none</div>
      )}
    </div>
  );
}

export function ResultsView({ state, onFeedback }) {
  const pi = state.project_input || {};
  const dp = state.draft_plan || {};
  const rep = state.validation_report || {};
  const rgl = state.risk_gap_list || { items: [] };
  const recs = state.recommendations || { items: [] };
  const op = state.optimized_plan || {};

  const score = op.compliance_score ?? rep.overall_compliance_score ?? 0;
  const findings = rep.findings || [];
  const nGap = findings.filter((f) => f.finding_type === "gap").length;
  const nRisk = findings.filter((f) => f.finding_type === "risk_flag").length;
  const nAlign = findings.filter((f) => f.finding_type === "alignment").length;

  const breakdown = [
    { name: "Alignments", key: "alignment", value: nAlign },
    { name: "Gaps", key: "gap", value: nGap },
    { name: "Risk flags", key: "risk_flag", value: nRisk },
  ].filter((d) => d.value > 0);

  const rankedItems = [...(rgl.items || [])].sort((a, b) => sevRank(a.severity) - sevRank(b.severity));

  return (
    <div className="animate-fade-in space-y-6">
      {/* Hero */}
      <Card>
        <CardContent className="flex flex-col items-center gap-8 p-6 md:flex-row">
          <ComplianceGauge score={score} />
          <div className="flex-1">
            <div className="text-xl font-bold">{op.project_title || pi.title || "Project"}</div>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{rep.alignment_summary}</p>
            <div className="mt-4 flex flex-wrap gap-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-warning/15 px-3 py-1 text-xs font-semibold text-warning">
                <CircleDashed className="h-3.5 w-3.5" /> {nGap} gaps
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-destructive/15 px-3 py-1 text-xs font-semibold text-destructive">
                <TriangleAlert className="h-3.5 w-3.5" /> {nRisk} risk flags
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/15 px-3 py-1 text-xs font-semibold text-primary">
                <Lightbulb className="h-3.5 w-3.5" /> {recs.items?.length || 0} recommendations
              </span>
              {rep.second_opinion && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-xs font-semibold text-secondary-foreground">
                  <Sparkles className="h-3.5 w-3.5" /> Gemini 2nd opinion
                </span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="validation">
        <TabsList>
          <TabsTrigger value="initiation">1 · Initiation</TabsTrigger>
          <TabsTrigger value="plan">2 · Draft Plan</TabsTrigger>
          <TabsTrigger value="validation">3 · Validation</TabsTrigger>
          <TabsTrigger value="gaps">4 · Gaps · Risks · Recs</TabsTrigger>
          <TabsTrigger value="optimized">5 · Optimized Plan</TabsTrigger>
        </TabsList>

        {/* Initiation */}
        <TabsContent value="initiation">
          <Card>
            <CardHeader><CardTitle>{pi.title}</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm leading-relaxed text-muted-foreground">{pi.summary}</p>
              <div className="grid gap-4 md:grid-cols-2">
                <List title="Objectives" items={pi.objectives} />
                <List title="Deliverables" items={pi.deliverables} />
                <List title="Constraints" items={pi.constraints} />
                <List title="Stakeholders" items={pi.stakeholders} />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Plan */}
        <TabsContent value="plan">
          <Card className="mb-4">
            <CardHeader><CardTitle>Approach</CardTitle></CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-muted-foreground">{dp.approach}</p>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <List title="Work breakdown structure" items={dp.wbs} />
                <List title="Milestones" items={dp.milestones} />
              </div>
            </CardContent>
          </Card>
          {(dp.sections || []).map((sec, i) => (
            <FindingCard key={i} title={sec.title} badges={[{ variant: "ka", label: sec.knowledge_area }]}>
              {sec.content}
            </FindingCard>
          ))}
        </TabsContent>

        {/* Validation */}
        <TabsContent value="validation">
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Per-section compliance</CardTitle></CardHeader>
              <CardContent><SectionScoresChart scores={rep.section_scores || []} /></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Findings breakdown</CardTitle></CardHeader>
              <CardContent><BreakdownPie data={breakdown} /></CardContent>
            </Card>
          </div>
          {rep.second_opinion && (
            <div className="my-4 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning">
              <Sparkles className="mr-1.5 inline h-4 w-4" /> Gemini 2nd opinion: {rep.second_opinion}
            </div>
          )}
          <h3 className="mb-3 mt-6 text-base font-semibold">Findings &amp; citations</h3>
          {findings.length ? findings.map((f, i) => {
            const Icon = f.finding_type === "gap" ? CircleDashed : f.finding_type === "risk_flag" ? TriangleAlert : CheckCircle2;
            return (
              <FindingCard key={i} title={f.statement}
                badges={[
                  { variant: f.finding_type, label: f.finding_type.replace("_", " ") },
                  { variant: f.severity, label: f.severity },
                  { variant: "ka", label: f.knowledge_area },
                ]}>
                {f.evidence && <div className="mb-1"><span className="font-semibold text-foreground">Reference says:</span> {f.evidence}</div>}
                <Citations items={f.citations} />
              </FindingCard>
            );
          }) : <div className="text-sm italic text-muted-foreground">No findings.</div>}
        </TabsContent>

        {/* Gaps / Risks / Recs */}
        <TabsContent value="gaps">
          <h3 className="mb-3 text-base font-semibold">Severity-ranked gaps &amp; risks</h3>
          {rankedItems.length ? rankedItems.map((it, i) => (
            <FindingCard key={i} title={it.title}
              badges={[
                { variant: it.category === "gap" ? "gap" : "risk", label: it.category },
                { variant: it.severity, label: it.severity },
                { variant: "ka", label: it.knowledge_area },
              ]}>
              <div>{it.description}</div>
              {it.mitigation && <div className="mt-2"><span className="font-semibold text-foreground">Mitigation:</span> {it.mitigation}</div>}
              <Citations items={it.citations} />
            </FindingCard>
          )) : <div className="text-sm italic text-muted-foreground">No gaps/risks.</div>}

          <h3 className="mb-3 mt-6 text-base font-semibold">Recommendations</h3>
          {(recs.items || []).length ? recs.items.map((r, i) => (
            <FindingCard key={i} title={r.recommendation}
              badges={[{ variant: r.priority, label: r.priority }, { variant: "ka", label: r.knowledge_area }]}>
              <div><span className="font-semibold text-foreground">Rationale:</span> {r.rationale}</div>
              {r.addresses && <div className="mt-1.5 text-xs text-muted-foreground">Addresses: {r.addresses}</div>}
              <Citations items={r.citations} />
            </FindingCard>
          )) : <div className="text-sm italic text-muted-foreground">No recommendations.</div>}
        </TabsContent>

        {/* Optimized */}
        <TabsContent value="optimized">
          <Card className="mb-4">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Executive summary</CardTitle>
              <Badge variant="low">compliance {op.compliance_score}</Badge>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-muted-foreground">{op.executive_summary}</p>
            </CardContent>
          </Card>
          {op.changes_from_draft?.length > 0 && (
            <div className="mb-4 rounded-xl border border-success/30 bg-success/5 p-4">
              <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-success">Changes from draft (diff)</div>
              <ul className="space-y-1.5 text-sm text-success">{op.changes_from_draft.map((c, i) => <li key={i}>+ {c}</li>)}</ul>
            </div>
          )}
          {(op.sections || []).map((sec, i) => (
            <FindingCard key={i} title={sec.title} badges={[{ variant: "ka", label: sec.knowledge_area }]}>
              {sec.content}
            </FindingCard>
          ))}
          {op.open_items?.length > 0 && <List title="Open items" items={op.open_items} />}
        </TabsContent>
      </Tabs>

      <FeedbackForm state={state} onSubmitted={onFeedback} />
    </div>
  );
}
