import {
  RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Cell, Tooltip, PieChart, Pie, Legend,
  RadarChart, PolarGrid, PolarRadiusAxis, Radar, Treemap,
} from "recharts";
import { scoreColor, cn } from "@/lib/utils";

const AXIS = "hsl(215 18% 60%)";

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

/* ---------- gauge ---------- */
export function ComplianceGauge({ score, size = 210, label = "compliance" }) {
  const data = [{ name: "v", value: score, fill: scoreColor(score) }];
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart innerRadius="72%" outerRadius="100%" data={data}
          startAngle={90} endAngle={-270}>
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar background={{ fill: "hsl(222 30% 16%)" }} dataKey="value" cornerRadius={20} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="font-extrabold tracking-tight" style={{ color: scoreColor(score), fontSize: size * 0.23 }}>{score}</div>
        <div className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</div>
      </div>
    </div>
  );
}

/* ---------- small progress ring ---------- */
export function Ring({ value, size = 64, label }) {
  const data = [{ name: "v", value, fill: scoreColor(value) }];
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative" style={{ width: size, height: size }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart innerRadius="66%" outerRadius="100%" data={data} startAngle={90} endAngle={-270}>
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar background={{ fill: "hsl(222 30% 16%)" }} dataKey="value" cornerRadius={10} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 grid place-items-center text-sm font-bold" style={{ color: scoreColor(value) }}>{value}</div>
      </div>
      {label && <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>}
    </div>
  );
}

/* ---------- radar of KA scores ---------- */
export function RadarKA({ data }) {
  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="hsl(222 30% 20%)" />
        <PolarAngleAxis dataKey="ka" tick={{ fill: AXIS, fontSize: 10 }} />
        <PolarRadiusAxis domain={[0, 100]} tick={{ fill: AXIS, fontSize: 9 }} axisLine={false} />
        <Radar dataKey="score" stroke="hsl(245 82% 67%)" fill="hsl(245 82% 67%)" fillOpacity={0.35} />
        <Tooltip content={<ChartTip />} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

/* ---------- per-section horizontal score bars ---------- */
export function SectionScoresChart({ scores }) {
  const data = scores.map((s) => ({ name: s.knowledge_area, score: s.score }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ left: 12, right: 24 }}>
        <XAxis type="number" domain={[0, 100]} stroke={AXIS} fontSize={11} tickLine={false} axisLine={false} />
        <YAxis dataKey="name" type="category" stroke={AXIS} fontSize={11} width={104} tickLine={false} axisLine={false} />
        <Tooltip content={<ChartTip />} cursor={{ fill: "hsl(222 30% 14%)" }} />
        <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={14}>
          {data.map((d, i) => <Cell key={i} fill={scoreColor(d.score)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ---------- KA compliance heatmap (colored grid) ---------- */
function heatColor(score) {
  // red(0) -> amber(50) -> green(100)
  const h = Math.max(0, Math.min(120, (score / 100) * 120));
  return `hsl(${h} 65% ${score == null ? 18 : 42}%)`;
}
export function KAHeatmap({ scores }) {
  // scores: [{knowledge_area, score}]
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {scores.map((s) => (
        <div key={s.knowledge_area}
          className="flex flex-col items-center justify-center rounded-lg p-3 text-center transition-transform hover:scale-[1.03]"
          style={{ background: heatColor(s.score), boxShadow: "inset 0 0 0 1px rgba(255,255,255,.06)" }}>
          <div className="text-lg font-extrabold text-white drop-shadow">{s.score}</div>
          <div className="mt-0.5 text-[10px] font-medium uppercase tracking-wide text-white/85">{s.knowledge_area}</div>
        </div>
      ))}
    </div>
  );
}

/* ---------- risk matrix: likelihood (rows) x impact (cols) heatmap ---------- */
const LV = ["low", "medium", "high"];
function cellColor(l, i) {
  const score = (LV.indexOf(l) + LV.indexOf(i)); // 0..4
  const map = ["hsl(152 55% 30%)", "hsl(110 50% 32%)", "hsl(45 80% 38%)",
    "hsl(25 80% 42%)", "hsl(0 70% 44%)"];
  return map[score];
}
export function RiskMatrix({ grid }) {
  return (
    <div>
      <div className="mb-1 text-center text-[10px] uppercase tracking-widest text-muted-foreground">Impact →</div>
      <div className="flex gap-2">
        <div className="flex flex-col justify-around pr-1 text-[10px] uppercase tracking-widest text-muted-foreground"
          style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>Likelihood →</div>
        <div className="grid flex-1 grid-cols-3 gap-1.5">
          {["high", "medium", "low"].map((l) => (
            LV.map((i) => {
              const n = grid[`${l}|${i}`] || 0;
              return (
                <div key={`${l}-${i}`}
                  className="relative flex aspect-[2/1] items-center justify-center rounded-md text-lg font-bold text-white"
                  style={{ background: cellColor(l, i), opacity: n ? 1 : 0.35 }}
                  title={`Likelihood ${l} × Impact ${i}: ${n}`}>
                  {n || ""}
                </div>
              );
            })
          ))}
        </div>
      </div>
      <div className="mt-1 flex justify-between px-7 text-[9px] uppercase tracking-wide text-muted-foreground">
        <span>low</span><span>med</span><span>high</span>
      </div>
    </div>
  );
}

/* ---------- donut from {label: count} ---------- */
const PALETTE = {
  alignment: "hsl(152 60% 48%)", gap: "hsl(38 92% 60%)", risk_flag: "hsl(0 72% 60%)",
  risk: "hsl(0 72% 60%)", high: "hsl(0 72% 60%)", medium: "hsl(38 92% 60%)",
  low: "hsl(152 60% 48%)",
};
export function DistributionDonut({ data }) {
  // data: [{name, key, value}]
  const total = data.reduce((a, d) => a + d.value, 0);
  if (!total) return <div className="py-6 text-sm italic text-muted-foreground">No data.</div>;
  return (
    <ResponsiveContainer width="100%" height={230}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={56} outerRadius={86} paddingAngle={3} strokeWidth={0}>
          {data.map((d, i) => <Cell key={i} fill={PALETTE[d.key] || "hsl(245 82% 67%)"} />)}
        </Pie>
        <Tooltip content={<ChartTip />} />
        <Legend formatter={(v) => <span className="text-xs text-muted-foreground">{v}</span>} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export { DistributionDonut as BreakdownPie };  // back-compat alias

/* ---------- generic horizontal category bars from {label:value} ---------- */
export function CategoryBar({ data, color = "hsl(245 82% 67%)" }) {
  if (!data.length) return <div className="py-6 text-sm italic text-muted-foreground">No data yet.</div>;
  return (
    <ResponsiveContainer width="100%" height={Math.max(200, data.length * 34)}>
      <BarChart data={data} layout="vertical" margin={{ left: 12, right: 24 }}>
        <XAxis type="number" allowDecimals={false} stroke={AXIS} fontSize={11} tickLine={false} axisLine={false} />
        <YAxis dataKey="name" type="category" stroke={AXIS} fontSize={12} width={120} tickLine={false} axisLine={false} />
        <Tooltip content={<ChartTip />} cursor={{ fill: "hsl(222 30% 14%)" }} />
        <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={16} fill={color} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ---------- treemap of KA concentration ---------- */
const TREE_COLORS = ["#6d7cff", "#8b6bff", "#a26bff", "#6b8bff", "#6bb6ff",
  "#5d7cff", "#7c6bff", "#9b6bff", "#6b9bff", "#7b8bff"];
function TreeCell(props) {
  const { x, y, width, height, name, value, index } = props;
  if (width < 4 || height < 4) return null;
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} rx={6}
        style={{ fill: TREE_COLORS[index % TREE_COLORS.length], stroke: "hsl(222 47% 6%)", strokeWidth: 2 }} />
      {width > 54 && height > 26 && (
        <text x={x + 8} y={y + 18} fill="#fff" fontSize={11} fontWeight={600}>{name}</text>
      )}
      {width > 54 && height > 40 && (
        <text x={x + 8} y={y + 34} fill="rgba(255,255,255,.8)" fontSize={11}>{value}</text>
      )}
    </g>
  );
}
export function ConcentrationTreemap({ data }) {
  // data: [{name, value}]
  if (!data.length) return <div className="py-6 text-sm italic text-muted-foreground">No data.</div>;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <Treemap data={data} dataKey="value" content={<TreeCell />} aspectRatio={1.4} isAnimationActive />
    </ResponsiveContainer>
  );
}

/* ---------- KPI stat tile ---------- */
export function StatTile({ label, value, sub, tone = "default", icon: Icon }) {
  const tones = {
    default: "text-foreground", ok: "text-success", warn: "text-warning",
    bad: "text-destructive", brand: "text-primary",
  };
  return (
    <div className="rounded-xl border border-border bg-gradient-to-br from-card to-background p-4 shadow-lg">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        {Icon && <Icon className={cn("h-4 w-4", tones[tone])} />}
      </div>
      <div className={cn("mt-1 text-3xl font-extrabold tracking-tight tabular-nums", tones[tone])}>{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}
