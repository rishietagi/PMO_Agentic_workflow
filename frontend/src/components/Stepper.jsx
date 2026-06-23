import { Check, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export const PIPELINE_STEPS = [
  { node: "intake", label: "Initiation" },
  { node: "plan_generation", label: "Plan" },
  { node: "validation", label: "Validation" },
  { node: "gap_risk", label: "Gap & Risk" },
  { node: "recommendations", label: "Recommendations" },
  { node: "finalization", label: "Finalization" },
];

// status map: { node: "done" | "active" | "pending" }
export function Stepper({ statusMap }) {
  return (
    <div className="flex flex-wrap gap-2">
      {PIPELINE_STEPS.map(({ node, label }, i) => {
        const st = statusMap[node] || "pending";
        return (
          <div
            key={node}
            className={cn(
              "flex items-center gap-2.5 rounded-full border px-3.5 py-2 text-[12.5px] transition-all duration-300",
              st === "active" && "border-primary text-foreground shadow-[0_0_0_1px_hsl(var(--primary)),0_8px_22px_-8px_hsl(var(--primary))]",
              st === "done" && "border-success/40 text-foreground",
              st === "pending" && "border-border text-muted-foreground"
            )}
          >
            <span
              className={cn(
                "grid h-5 w-5 place-items-center rounded-full text-[10px] font-bold",
                st === "done" && "bg-success text-background",
                st === "active" && "bg-primary/20 text-primary",
                st === "pending" && "border border-muted-foreground/40"
              )}
            >
              {st === "done" ? <Check className="h-3 w-3" /> : st === "active" ? <Loader2 className="h-3 w-3 animate-spin" /> : i + 1}
            </span>
            {label}
          </div>
        );
      })}
    </div>
  );
}
