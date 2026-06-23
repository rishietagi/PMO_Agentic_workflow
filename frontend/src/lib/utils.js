import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export const scoreColor = (s) =>
  s >= 75 ? "hsl(152 60% 48%)" : s >= 55 ? "hsl(38 92% 60%)" : "hsl(0 72% 60%)";

export const sevRank = (s) => ({ high: 0, medium: 1, low: 2 }[s] ?? 1);
