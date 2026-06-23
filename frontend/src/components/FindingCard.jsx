import * as React from "react";
import { ChevronDown, BookOpen } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function Citations({ items }) {
  if (!items || !items.length)
    return <span className="text-xs italic text-muted-foreground">no citation</span>;
  return (
    <div className="mt-2.5 flex flex-wrap gap-2">
      {items.map((c, i) => {
        const pages =
          c.page_start === c.page_end ? `p.${c.page_start}` : `pp.${c.page_start}-${c.page_end}`;
        const book = ({ RITA_10th_Edition: "RITA", PMBOK_Guide_6th: "PMBOK" }[c.knowledge_base]) || "REF";
        return (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/10 px-2 py-0.5 font-mono text-[11px] text-primary"
          >
            <BookOpen className="h-3 w-3" />
            {book} Ch.{c.chapter_number} · {pages}
          </span>
        );
      })}
    </div>
  );
}

/** Collapsible card used for findings, risks, recommendations, sections. */
export function FindingCard({ badges = [], title, children, defaultOpen = false }) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="mb-2.5 overflow-hidden rounded-xl border border-border bg-card/60">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2.5 px-4 py-3 text-left transition-colors hover:bg-accent/40"
      >
        {badges.map((b, i) => (
          <Badge key={i} variant={b.variant}>
            {b.label}
          </Badge>
        ))}
        <span className="flex-1 text-sm font-medium">{title}</span>
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
        />
      </button>
      {open && <div className="border-t border-border px-4 py-3 text-[13.5px] leading-relaxed text-muted-foreground">{children}</div>}
    </div>
  );
}
