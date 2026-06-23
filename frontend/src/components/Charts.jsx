import {
  RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Cell, Tooltip, PieChart, Pie, Legend,
} from "recharts";
import { scoreColor } from "@/lib/utils";

const AXIS = "hsl(215 18% 60%)";
const GRID = "hsl(222 30% 18%)";

function ChartTip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-xl">
      {label != null && <div className="mb-1 font-semibold">{label}</div>}
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || p.payload?.fill }}>
          {p.name}: <span className="font-semibold">{p.value}</span>
        </div>
      ))}
    </div>
  );
}

/** Big radial compliance gauge. */
export function ComplianceGauge({ score }) {
  const data = [{ name: "compliance", value: score, fill: scoreColor(score) }];
  return (
    <div className="relative h-[210px] w-[210px]">
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          innerRadius="74%" outerRadius="100%" data={data}
          startAngle={90} endAngle={-270}
        >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar background={{ fill: "hsl(222 30% 16%)" }} dataKey="value" cornerRadius={20} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-5xl font-extrabold tracking-tight" style={{ color: scoreColor(score) }}>
          {score}
        </div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">
          / 100 compliance
        </div>
      </div>
    </div>
  );
}

/** Horizontal bar chart of per-section compliance scores. */
export function SectionScoresChart({ scores }) {
  const data = scores.map((s) => ({ name: s.knowledge_area, score: s.score }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 34)}>
      <BarChart data={data} layout="vertical" margin={{ left: 12, right: 24 }}>
        <XAxis type="number" domain={[0, 100]} stroke={AXIS} fontSize={11} tickLine={false} axisLine={false} />
        <YAxis dataKey="name" type="category" stroke={AXIS} fontSize={12} width={110} tickLine={false} axisLine={false} />
        <Tooltip content={<ChartTip />} cursor={{ fill: "hsl(222 30% 14%)" }} />
        <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={16}>
          {data.map((d, i) => <Cell key={i} fill={scoreColor(d.score)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

const PIE_COLORS = {
  gap: "hsl(38 92% 60%)", risk_flag: "hsl(0 72% 60%)", alignment: "hsl(152 60% 48%)",
  risk: "hsl(0 72% 60%)",
};

/** Donut of finding-type or gap/risk breakdown. */
export function BreakdownPie({ data }) {
  const total = data.reduce((a, d) => a + d.value, 0);
  if (!total) return <div className="py-6 text-sm italic text-muted-foreground">No data.</div>;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%"
             innerRadius={58} outerRadius={88} paddingAngle={3} strokeWidth={0}>
          {data.map((d, i) => <Cell key={i} fill={PIE_COLORS[d.key] || "hsl(245 82% 67%)"} />)}
        </Pie>
        <Tooltip content={<ChartTip />} />
        <Legend formatter={(v) => <span className="text-xs text-muted-foreground">{v}</span>} />
      </PieChart>
    </ResponsiveContainer>
  );
}

/** Generic vertical bar chart (dashboard gap areas). */
export function CategoryBar({ data, color = "hsl(245 82% 67%)" }) {
  if (!data.length) return <div className="py-6 text-sm italic text-muted-foreground">No data yet.</div>;
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 38)}>
      <BarChart data={data} layout="vertical" margin={{ left: 12, right: 24 }}>
        <XAxis type="number" allowDecimals={false} stroke={AXIS} fontSize={11} tickLine={false} axisLine={false} />
        <YAxis dataKey="name" type="category" stroke={AXIS} fontSize={12} width={120} tickLine={false} axisLine={false} />
        <Tooltip content={<ChartTip />} cursor={{ fill: "hsl(222 30% 14%)" }} />
        <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={18} fill={color} />
      </BarChart>
    </ResponsiveContainer>
  );
}
