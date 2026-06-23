import { Compass, Play, BarChart3, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

function StatusRow({ label, ok, okText, badText }) {
  return (
    <div className="flex items-center justify-between py-1 text-[13px] text-muted-foreground">
      <span>{label}</span>
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
          ok ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive"
        )}
      >
        {ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
        {ok ? okText : badText}
      </span>
    </div>
  );
}

export function Sidebar({ view, setView, status }) {
  const s = status || {};
  return (
    <aside className="flex h-screen w-[290px] shrink-0 flex-col gap-6 border-r border-border bg-card/40 p-6 glass">
      <div className="flex items-center gap-3">
        <div className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-primary to-violet-500 shadow-lg shadow-primary/40">
          <Compass className="h-6 w-6 text-white" />
        </div>
        <div>
          <div className="text-[15px] font-extrabold leading-tight tracking-tight">PMO Intelligence</div>
          <div className="text-[11px] text-muted-foreground">Closed-loop optimization · POC</div>
        </div>
      </div>

      <nav className="flex flex-col gap-1.5">
        {[
          { id: "run", label: "Run pipeline", icon: Play },
          { id: "dashboard", label: "Feedback dashboard", icon: BarChart3 },
        ].map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setView(id)}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all",
              view === id
                ? "bg-gradient-to-br from-primary/20 to-violet-500/10 text-foreground ring-1 ring-border"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </nav>

      <div className="rounded-xl border border-border bg-card/60 p-4">
        <div className="mb-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          System status
        </div>
        <StatusRow label="Knowledge base" ok={s.kb_built} okText={`${s.kb_chunks} chunks`} badText="not built" />
        <StatusRow label="Groq key" ok={s.groq_key} okText="ready" badText="missing" />
        <StatusRow label="Gemini fallback" ok={s.google_key} okText="ready" badText="off" />
        {s.models && (
          <div className="mt-3 font-mono text-[10.5px] leading-relaxed text-muted-foreground/80">
            reason: {s.models.reasoning}
            <br />
            cheap: {s.models.cheap}
            <br />
            fallback: {s.models.fallback}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card/60 p-4">
        <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Why this matters
        </div>
        <ul className="space-y-1.5 text-[12.5px] text-muted-foreground">
          <li>• Reduced planning effort</li>
          <li>• Improved governance &amp; quality</li>
          <li>• Faster project readiness</li>
          <li>• Consistency across teams</li>
        </ul>
      </div>

      <div className="mt-auto text-[11px] text-muted-foreground/70">
        Grounded in RITA PMP Prep · every finding cited
      </div>
    </aside>
  );
}
