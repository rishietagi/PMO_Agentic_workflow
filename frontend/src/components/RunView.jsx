import * as React from "react";
import { Play, Loader2, Sparkles, AlertTriangle, Upload, FileText, Download } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Stepper, PIPELINE_STEPS } from "@/components/Stepper";
import { ResultsView } from "@/components/ResultsView";
import { getSampleSow, runPipeline, uploadSowPdf } from "@/lib/api";

export function RunView({ status, onFeedback }) {
  const [sow, setSow] = React.useState("");
  const [secondOpinion, setSecondOpinion] = React.useState(false);
  const [iterations, setIterations] = React.useState("1");
  const [running, setRunning] = React.useState(false);
  const [statusMap, setStatusMap] = React.useState({});
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState("");
  const [started, setStarted] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [source, setSource] = React.useState(null);  // {filename, pages, chars}
  const fileRef = React.useRef(null);

  React.useEffect(() => { getSampleSow().then((d) => setSow(d.sow || d)).catch(() => {}); }, []);

  async function onPickFile(e) {
    const f = e.target.files?.[0];
    e.target.value = "";  // allow re-selecting the same file
    if (!f) return;
    setUploading(true); setError(""); setSource(null);
    try {
      const r = await uploadSowPdf(f);
      setSow(r.sow);
      setSource({ filename: r.filename, pages: r.pages, chars: r.chars });
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  const canRun = status?.can_run && !running && sow.trim().length > 0;

  async function run() {
    setRunning(true); setError(""); setResult(null); setStarted(true);
    const init = {}; PIPELINE_STEPS.forEach((s) => (init[s.node] = "pending"));
    setStatusMap(init);
    try {
      await runPipeline(
        { sow, second_opinion: secondOpinion, max_iterations: parseInt(iterations, 10) },
        (ev) => {
          if (ev.type === "progress" && ev.node !== "start") {
            setStatusMap((prev) => {
              const next = { ...prev };
              Object.keys(next).forEach((k) => { if (next[k] === "active") next[k] = "done"; });
              next[ev.node] = "active";
              return next;
            });
          } else if (ev.type === "result") {
            setStatusMap((prev) => {
              const next = { ...prev };
              Object.keys(next).forEach((k) => (next[k] = "done"));
              return next;
            });
            setResult(ev.state);
          } else if (ev.type === "error") {
            setError(ev.message);
          }
        }
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-extrabold tracking-tight">Closed-Loop PMO Optimization</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Turn a Statement of Work into a validated, PMI-aligned plan with a compliance score and
          page-level citations.
        </p>
      </header>

      {!status?.can_run && (
        <div className="flex items-center gap-2 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning">
          <AlertTriangle className="h-4 w-4" />
          {!status?.kb_built ? "Knowledge base not built — run the ingestion scripts." : "No API key configured in .env."}
        </div>
      )}

      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle>Statement of Work / RFP</CardTitle>
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
              <Switch checked={secondOpinion} onCheckedChange={setSecondOpinion} disabled={!status?.google_key} />
              Gemini 2nd opinion
            </label>
            <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
              Iterations
              <Select value={iterations} onValueChange={setIterations}>
                <SelectTrigger className="h-8 w-16"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1</SelectItem>
                  <SelectItem value="2">2</SelectItem>
                  <SelectItem value="3">3</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Upload row */}
          <input ref={fileRef} type="file" accept="application/pdf,.pdf"
                 onChange={onPickFile} className="hidden" />
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="default" size="sm" onClick={() => fileRef.current?.click()}
                    disabled={uploading}>
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              {uploading ? "Extracting…" : "Upload PDF (SOW / RFP)"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => getSampleSow().then((d) => { setSow(d.sow || d); setSource(null); })}>
              <FileText className="h-4 w-4" /> Load sample text
            </Button>
            <a href="/api/sample-sow.pdf" className="inline-flex items-center gap-1.5 text-[13px] text-primary hover:underline">
              <Download className="h-3.5 w-3.5" /> sample SOW (PDF)
            </a>
          </div>
          {source && (
            <div className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-[13px] text-success">
              <FileText className="h-4 w-4" />
              Extracted <b>{source.chars.toLocaleString()}</b> chars from
              <b>&nbsp;{source.filename}</b> ({source.pages} pages) — review/edit below, then run.
            </div>
          )}
          <Textarea value={sow} onChange={(e) => { setSow(e.target.value); }}
                    placeholder="Upload a SOW/RFP PDF above, or paste the text here…" />
          <div className="flex items-center gap-4">
            <Button onClick={run} disabled={!canRun}>
              {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {running ? "Running…" : "Run pipeline"}
            </Button>
            {running && (
              <span className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
                <Sparkles className="h-3.5 w-3.5" /> first run loads models (~15s)
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {started && (
        <div className="rounded-xl border border-border bg-card/40 p-4">
          <Stepper statusMap={statusMap} />
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {result && <ResultsView state={result} onFeedback={onFeedback} />}
    </div>
  );
}
