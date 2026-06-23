import * as React from "react";
import { Star } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { submitFeedback } from "@/lib/api";
import { cn } from "@/lib/utils";

export function FeedbackForm({ state, onSubmitted }) {
  const [rating, setRating] = React.useState(4);
  const [helpful, setHelpful] = React.useState(true);
  const [comment, setComment] = React.useState("");
  const [done, setDone] = React.useState(false);

  async function submit() {
    const op = state.optimized_plan || {};
    const gaps = (state.risk_gap_list?.items || []).map((i) => ({
      knowledge_area: i.knowledge_area, category: i.category,
      severity: i.severity, title: i.title,
    }));
    await submitFeedback({
      run_id: state.run_id || "", project_title: op.project_title || "",
      compliance_score: op.compliance_score || 0, rating, helpful, comment,
      gap_events: gaps,
    });
    setDone(true);
    onSubmitted?.();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          📝 Feedback <span className="text-sm font-normal text-muted-foreground">(flow step 7)</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">Quality</span>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} onClick={() => setRating(n)}>
                <Star className={cn("h-5 w-5 transition-colors", n <= rating ? "fill-warning text-warning" : "text-muted-foreground/40")} />
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <Switch checked={helpful} onCheckedChange={setHelpful} id="helpful" />
          <label htmlFor="helpful" className="text-sm text-muted-foreground">This was helpful</label>
        </div>
        <Textarea placeholder="Comments…" value={comment} onChange={(e) => setComment(e.target.value)} className="min-h-[80px]" />
        <div className="flex items-center gap-3">
          <Button onClick={submit}>Submit feedback</Button>
          {done && <span className="text-sm text-success">✓ Recorded — see the Feedback dashboard.</span>}
        </div>
      </CardContent>
    </Card>
  );
}
