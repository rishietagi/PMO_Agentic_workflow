import * as React from "react";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md px-2 py-0.5 text-[10.5px] font-bold uppercase tracking-wide transition-colors",
  {
    variants: {
      variant: {
        default: "bg-secondary text-secondary-foreground",
        outline: "border border-border text-muted-foreground",
        high: "bg-destructive/15 text-destructive",
        medium: "bg-warning/15 text-warning",
        low: "bg-success/15 text-success",
        gap: "bg-warning/15 text-warning",
        risk: "bg-destructive/15 text-destructive",
        risk_flag: "bg-destructive/15 text-destructive",
        alignment: "bg-success/15 text-success",
        ka: "bg-primary/15 text-primary",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

function Badge({ className, variant, ...props }) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
