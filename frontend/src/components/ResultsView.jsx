import * as React from "react";
import { motion } from "framer-motion";
import {
  FileSearch, ListTree, ShieldCheck, TriangleAlert, Lightbulb, Rocket,
  CircleDashed, CheckCircle2, ArrowUpRight, Check, X,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FindingCard, Citations } from "@/components/FindingCard";
import { FeedbackForm } from "@/components/FeedbackForm";
import { ExecutiveDashboard } from "@/components/ExecutiveDashboard";
import {
  ComplianceGauge, SectionScoresChart, KAHeatmap, DistributionDonut,
  CategoryBar, ConcentrationTreemap, StatTile, RiskMatrix,
} from "@/components/Charts";
import {
  kaScores, findingCounts, riskItems, riskMatrix, severityDist,
  kaConcentration, priorityDist, planCoverage, KNOWLEDGE_AREAS,
} from "@/lib/analytics";
import { sevRank } from "@/lib/utils";

const STEPS = {
  initiation: { icon: FileSearch, title: "Project Initiation",
    blurb: "Extracts a structured project definition from the raw SOW / RFP — objectives, scope, deliverables, constraints, and stakeholders — so every later stage reasons from one consistent baseline." },
  plan: { icon: ListTree, title: "AI Plan Generation",
    blurb: "Generates a first-pass, PMI-aligned plan: an approach, a work-breakdown structure, milestones, and a dedicated section for each of the ten knowledge areas." },
  validation: { icon: ShieldCheck, title: "PMO Validation (core)",
    blurb: "Each plan section is validated against the PMBOK knowledge base via hybrid RAG, producing per-area compliance scores and cited findings — alignments, gaps, and risk flags." },
  gaps: { icon: TriangleAlert, title: "Gap & Risk Identification",
    blurb: "Consolidates and severity-ranks gaps and risks, cross-referencing risk-management guidance, with likelihood, impact, and concrete mitigations." },
  recs: { icon: Lightbulb, title: "AI Recommendations",
    blurb: "Prioritized, RAG-grounded actions that close the gaps and mitigate the risks — each one citing the exact source page it draws from." },
  optimized: { icon: Rocket, title: "Optimized Plan",
    blurb: "The refined plan with recommendations applied, an executive summary, and a clear diff versus the original draft." },
};

function StepIntro({ id }) {
  const s = STEPS[id]; const Icon = s.icon;
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="mb-5 flex items-start gap-3 rounded-xl border border-border bg-gradient-to-br from-primary/10 to-transparent p-4">
      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary/15 text-primary"><Icon className="h-5 w-5" /></div>
      <div>
        <div className="font-bold">{s.title}</div>
        <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">{s.blurb}</p>
      </div>
    </motion.div>
  );
}

function List({ title, items }) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{title}</div>
      {items && items.length
        ? <ul className="space-y-1.5 text-sm leading-relaxed">{items.map((x, i) => <li key={i}>• {x}</li>)}</ul>
        : <div className="text-sm italic text-muted-foreground">none</div>}
    </div>
  );
}

const TABS = [
  ["initiation", "1 · Initiation"], ["plan", "2 · Plan"],
  ["validation", "3 · Validation"], ["gaps", "4 · Gaps & Risks"],
  ["recs", "5 · Recommendations"], ["optimized", "6 · Optimized"],
];

export function ResultsView({ state, onFeedback }) {
  const pi = state.project_input || {};
  const dp = state.draft_plan || {};
  const rep = state.validation_report || {};
  const rgl = state.risk_gap_list || { items: [] };
  const recs = state.recommendations || { items: [] };
  const op = state.optimized_plan || {};

  const fc = findingCounts(state);
  const items = riskItems(state);
  const scoresMap = kaScores(state);
  const heat = KNOWLEDGE_AREAS.map((ka) => ({ knowledge_area: ka, score: scoresMap[ka] ?? 0 }));
  const findingDonut = [
    { name: "Aligned", key: "alignment", value: fc.alignment },
    { name: "Gaps", key: "gap", value: fc.gap },
    { name: "Risk flags", key: "risk_flag", value: fc.risk_flag },
  ].filter((d) => d.value);

  const draftScore = rep.overall_compliance_score ?? 0;
  const optScore = op.compliance_score ?? draftScore;
  const delta = optScore - draftScore;

  return (
    <div className="animate-fade-in space-y-7">
      {/* Unified executive dashboard */}
      <ExecutiveDashboard state={state} />

      <div className="border-t border-border pt-2">
        <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-muted-foreground">Stage-by-stage breakdown</h3>
        <Tabs defaultValue="validation">
          <TabsList>
            {TABS.map(([v, label]) => <TabsTrigger key={v} value={v}>{label}</TabsTrigger>)}
          </TabsList>

          {/* 1 — Initiation */}
          <TabsContent value="initiation">
            <StepIntro id="initiation" />
            <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
              {[["Objectives", pi.objectives], ["Deliverables", pi.deliverables],
                ["Requirements", pi.requirements], ["Constraints", pi.constraints],
                ["Stakeholders", pi.stakeholders]].map(([l, a]) =>
                <StatTile key={l} label={l} value={(a || []).length} tone="brand" />)}
            </div>
            <Card className="mb-4">
              <CardHeader><CardTitle>{pi.title}</CardTitle></CardHeader>
              <CardContent><p className="text-sm leading-relaxed text-muted-foreground">{pi.summary}</p></CardContent>
            </Card>
            <div className="grid gap-4 md:grid-cols-2">
              <List title="Objectives" items={pi.objectives} />
              <List title="Deliverables" items={pi.deliverables} />
              <List title="Constraints" items={pi.constraints} />
              <List title="Stakeholders" items={pi.stakeholders} />
            </div>
          </TabsContent>

          {/* 2 — Plan */}
          <TabsContent value="plan">
            <StepIntro id="plan" />
            <div className="mb-4 grid grid-cols-3 gap-3">
              <StatTile label="WBS items" value={(dp.wbs || []).length} tone="brand" icon={ListTree} />
              <StatTile label="Milestones" value={(dp.milestones || []).length} tone="ok" />
              <StatTile label="KA sections" value={(dp.sections || []).length} tone="default" />
            </div>
            <Card className="mb-4">
              <CardHeader><CardTitle>Knowledge-area coverage</CardTitle></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                  {planCoverage(state).map((c) => (
                    <div key={c.ka} className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-xs font-medium ${c.covered ? "border-success/40 bg-success/10 text-success" : "border-border bg-card/60 text-muted-foreground"}`}>
                      {c.covered ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}{c.ka}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
            <Card className="mb-4"><CardHeader><CardTitle>Approach</CardTitle></CardHeader>
              <CardContent><p className="text-sm leading-relaxed text-muted-foreground">{dp.approach}</p>
                <div className="mt-4 grid gap-4 md:grid-cols-2"><List title="WBS" items={dp.wbs} /><List title="Milestones" items={dp.milestones} /></div>
              </CardContent></Card>
            {(dp.sections || []).map((sec, i) => (
              <FindingCard key={i} title={sec.title} badges={[{ variant: "ka", label: sec.knowledge_area }]}>{sec.content}</FindingCard>
            ))}
          </TabsContent>

          {/* 3 — Validation */}
          <TabsContent value="validation">
            <StepIntro id="validation" />
            <div className="grid gap-5 lg:grid-cols-3">
              <Card><CardHeader><CardTitle>Overall compliance</CardTitle></CardHeader>
                <CardContent className="flex justify-center"><ComplianceGauge score={rep.overall_compliance_score ?? 0} size={180} /></CardContent></Card>
              <Card><CardHeader><CardTitle>Per-section scores</CardTitle></CardHeader>
                <CardContent><SectionScoresChart scores={rep.section_scores || []} /></CardContent></Card>
              <Card><CardHeader><CardTitle>Findings breakdown</CardTitle></CardHeader>
                <CardContent><DistributionDonut data={findingDonut} /></CardContent></Card>
            </div>
            <Card className="my-5"><CardHeader><CardTitle>Compliance heatmap</CardTitle></CardHeader>
              <CardContent><KAHeatmap scores={heat} /></CardContent></Card>
            {rep.second_opinion && (
              <div className="mb-4 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning">🔎 Gemini 2nd opinion: {rep.second_opinion}</div>
            )}
            <h3 className="mb-3 text-base font-semibold">Findings &amp; citations</h3>
            {(rep.findings || []).map((f, i) => {
              const Icon = f.finding_type === "gap" ? CircleDashed : f.finding_type === "risk_flag" ? TriangleAlert : CheckCircle2;
              return (
                <FindingCard key={i} title={f.statement}
                  badges={[{ variant: f.finding_type, label: f.finding_type.replace("_", " ") },
                    { variant: f.severity, label: f.severity }, { variant: "ka", label: f.knowledge_area }]}>
                  {f.evidence && <div className="mb-1"><span className="font-semibold text-foreground">Reference says:</span> {f.evidence}</div>}
                  <Citations items={f.citations} />
                </FindingCard>
              );
            })}
          </TabsContent>

          {/* 4 — Gaps & Risks */}
          <TabsContent value="gaps">
            <StepIntro id="gaps" />
            <div className="grid gap-5 lg:grid-cols-3">
              <Card><CardHeader><CardTitle>Risk matrix</CardTitle></CardHeader>
                <CardContent><RiskMatrix grid={riskMatrix(state)} /></CardContent></Card>
              <Card><CardHeader><CardTitle>Severity split</CardTitle></CardHeader>
                <CardContent><DistributionDonut data={[
                  { name: "High", key: "high", value: severityDist(items).high },
                  { name: "Medium", key: "medium", value: severityDist(items).medium },
                  { name: "Low", key: "low", value: severityDist(items).low }].filter((d) => d.value)} /></CardContent></Card>
              <Card><CardHeader><CardTitle>Concentration by area</CardTitle></CardHeader>
                <CardContent><ConcentrationTreemap data={Object.entries(kaConcentration(items)).map(([name, value]) => ({ name, value }))} /></CardContent></Card>
            </div>
            <h3 className="mb-3 mt-5 text-base font-semibold">Severity-ranked gaps &amp; risks</h3>
            {[...items].sort((a, b) => sevRank(a.severity) - sevRank(b.severity)).map((it, i) => (
              <FindingCard key={i} title={it.title}
                badges={[{ variant: it.category === "gap" ? "gap" : "risk", label: it.category },
                  { variant: it.severity, label: it.severity }, { variant: "ka", label: it.knowledge_area }]}>
                <div>{it.description}</div>
                {(it.likelihood || it.impact) && <div className="mt-1.5 text-xs text-muted-foreground">Likelihood: {it.likelihood || "—"} · Impact: {it.impact || "—"}</div>}
                {it.mitigation && <div className="mt-2"><span className="font-semibold text-foreground">Mitigation:</span> {it.mitigation}</div>}
                <Citations items={it.citations} />
              </FindingCard>
            ))}
          </TabsContent>

          {/* 5 — Recommendations */}
          <TabsContent value="recs">
            <StepIntro id="recs" />
            <div className="grid gap-5 lg:grid-cols-2">
              <Card><CardHeader><CardTitle>Priority distribution</CardTitle></CardHeader>
                <CardContent><DistributionDonut data={[
                  { name: "High", key: "high", value: priorityDist(state).high },
                  { name: "Medium", key: "medium", value: priorityDist(state).medium },
                  { name: "Low", key: "low", value: priorityDist(state).low }].filter((d) => d.value)} /></CardContent></Card>
              <Card><CardHeader><CardTitle>Recommendations by area</CardTitle></CardHeader>
                <CardContent><CategoryBar data={Object.entries(kaConcentration(recs.items || [])).map(([name, value]) => ({ name, value }))} /></CardContent></Card>
            </div>
            <h3 className="mb-3 mt-5 text-base font-semibold">Prioritized recommendations</h3>
            {(recs.items || []).map((r, i) => (
              <FindingCard key={i} title={r.recommendation}
                badges={[{ variant: r.priority, label: r.priority }, { variant: "ka", label: r.knowledge_area }]}>
                <div><span className="font-semibold text-foreground">Rationale:</span> {r.rationale}</div>
                {r.addresses && <div className="mt-1.5 text-xs text-muted-foreground">Addresses: {r.addresses}</div>}
                <Citations items={r.citations} />
              </FindingCard>
            ))}
          </TabsContent>

          {/* 6 — Optimized */}
          <TabsContent value="optimized">
            <StepIntro id="optimized" />
            <div className="mb-4 grid grid-cols-3 gap-3">
              <StatTile label="Draft compliance" value={draftScore} tone="warn" />
              <StatTile label="Optimized" value={optScore} tone="ok" icon={ArrowUpRight} />
              <StatTile label="Improvement" value={`${delta >= 0 ? "+" : ""}${delta}`} sub="points" tone={delta > 0 ? "ok" : "default"} />
            </div>
            <Card className="mb-4"><CardHeader className="flex-row items-center justify-between">
              <CardTitle>Executive summary</CardTitle><Badge variant="low">compliance {optScore}</Badge></CardHeader>
              <CardContent><p className="text-sm leading-relaxed text-muted-foreground">{op.executive_summary}</p></CardContent></Card>
            {op.changes_from_draft?.length > 0 && (
              <div className="mb-4 rounded-xl border border-success/30 bg-success/5 p-4">
                <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-success">Changes from draft (diff)</div>
                <ul className="space-y-1.5 text-sm text-success">{op.changes_from_draft.map((c, i) => <li key={i}>+ {c}</li>)}</ul>
              </div>
            )}
            {(op.sections || []).map((sec, i) => (
              <FindingCard key={i} title={sec.title} badges={[{ variant: "ka", label: sec.knowledge_area }]}>{sec.content}</FindingCard>
            ))}
            {op.open_items?.length > 0 && <List title="Open items" items={op.open_items} />}
          </TabsContent>
        </Tabs>
      </div>

      <FeedbackForm state={state} onSubmitted={onFeedback} />
    </div>
  );
}
