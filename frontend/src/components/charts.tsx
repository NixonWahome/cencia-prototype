import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Validated with the dataviz palette checker (light surface): CVD ΔE 9.4, normal ΔE 25.4.
export const SERIES = { reported: "#1F7A4D", expected: "#D97706" };
const GRID = "#ECE9E1";
const AXIS = "#8A938D";

const axisProps = { stroke: AXIS, fontSize: 11, tickLine: false, axisLine: false } as const;
const hhmmTick = (v: string) => v.slice(11, 16);

function ChartTooltip({ active, payload, label, unit }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-ink-muted">{String(label).replace("T", " ").slice(0, 16)}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-ink">
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-ink-muted">{p.name}</span>
          <span className="ml-auto font-semibold tabular-nums">
            {typeof p.value === "number" ? p.value.toFixed(unit === "Hz" ? 3 : 1) : p.value} {unit}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Reported vs physics-expected power: same unit, one axis. */
export function PowerChart({ data, height = 260 }: { data: { ts: string; ac_power_kw: number; expected_kw?: number }[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="ts" tickFormatter={hhmmTick} minTickGap={40} {...axisProps} />
        <YAxis {...axisProps} width={48} />
        <Tooltip content={<ChartTooltip unit="kW" />} cursor={{ stroke: AXIS, strokeDasharray: "3 3" }} />
        <Legend verticalAlign="top" align="right" height={24} iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
        <Line name="Physics-expected" dataKey="expected_kw" stroke={SERIES.expected} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
        <Line name="Reported" dataKey="ac_power_kw" stroke={SERIES.reported} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Single-series small multiple (the title names the series, so no legend). */
export function MetricChart({
  data,
  dataKey,
  unit,
  height = 150,
  area,
  domain,
  refLines = [],
}: {
  data: any[];
  dataKey: string;
  unit: string;
  height?: number;
  area?: boolean;
  domain?: [number | string, number | string];
  refLines?: number[];
}) {
  const common = { data, margin: { top: 8, right: 12, bottom: 0, left: -8 } };
  const body = (
    <>
      <CartesianGrid stroke={GRID} vertical={false} />
      <XAxis dataKey="ts" tickFormatter={hhmmTick} minTickGap={40} {...axisProps} />
      <YAxis {...axisProps} width={48} domain={domain ?? ["auto", "auto"]} tickFormatter={(v: number) => (unit === "Hz" ? v.toFixed(2) : String(Math.round(v)))} />
      <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ stroke: AXIS, strokeDasharray: "3 3" }} />
      {refLines.map((y) => (
        <ReferenceLine key={y} y={y} stroke="#B42318" strokeDasharray="4 4" strokeWidth={1} />
      ))}
    </>
  );
  return (
    <ResponsiveContainer width="100%" height={height}>
      {area ? (
        <AreaChart {...common}>
          {body}
          <Area name={unit} dataKey={dataKey} stroke={SERIES.expected} fill={SERIES.expected} fillOpacity={0.12} strokeWidth={2} isAnimationActive={false} />
        </AreaChart>
      ) : (
        <LineChart {...common}>
          {body}
          <Line name={unit} dataKey={dataKey} stroke={SERIES.reported} strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      )}
    </ResponsiveContainer>
  );
}

export function Sparkline({ data }: { data: { ts: string; ac_power_kw: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={48}>
      <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <Area dataKey="ac_power_kw" stroke={SERIES.reported} fill={SERIES.reported} fillOpacity={0.1} strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Daily reported vs verified energy (grouped bars, 2px gap, rounded data-ends). */
export function DailyEnergyChart({ data }: { data: { date: string; reported_kwh: number; verified_kwh: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -4 }} barGap={2} barCategoryGap="28%">
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} {...axisProps} />
        <YAxis {...axisProps} width={56} tickFormatter={(v: number) => `${Math.round(v / 1000)}k`} />
        <Tooltip content={<ChartTooltip unit="kWh" />} cursor={{ fill: "rgba(27,67,50,0.05)" }} />
        <Legend verticalAlign="top" align="right" height={24} wrapperStyle={{ fontSize: 12 }} />
        <Bar name="Reported" dataKey="reported_kwh" fill={SERIES.expected} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        <Bar name="Verified" dataKey="verified_kwh" fill={SERIES.reported} radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
