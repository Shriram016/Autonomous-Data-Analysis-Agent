import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Chart } from "../api";
import { formatAxis, formatNumber } from "../format";

type Props = { chart: Chart };

/** The chart the backend chose (line for time, bar for categories). The tooltip shows the
 *  exact value in the table's format; the axis shows a short form. */
export function AnswerChart({ chart }: Props) {
  const data = chart.points.map((p) => ({ x: p.x, y: p.y }));
  const tooltip = (
    <Tooltip
      formatter={(value) => [formatNumber(Number(value), chart.unit), chart.y_label]}
      labelStyle={{ color: "var(--ink)" }}
      contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)" }}
    />
  );
  const grid = <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" vertical={false} />;
  const yAxis = (
    <YAxis
      tickFormatter={(v: number) => formatAxis(v, chart.unit)}
      stroke="var(--muted)"
      width={72}
      fontSize={12}
    />
  );

  return (
    <figure className="chart" aria-label={`${chart.y_label} by ${chart.x_label}`}>
      <ResponsiveContainer width="100%" height={280}>
        {chart.kind === "line" ? (
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            {grid}
            <XAxis dataKey="x" stroke="var(--muted)" fontSize={12} minTickGap={16} />
            {yAxis}
            {tooltip}
            <Line type="monotone" dataKey="y" stroke="var(--accent)" strokeWidth={2} dot={false} />
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            {grid}
            <XAxis dataKey="x" stroke="var(--muted)" fontSize={12} interval={0} angle={-35} textAnchor="end" height={70} />
            {yAxis}
            {tooltip}
            <Bar dataKey="y" fill="var(--accent)" radius={[3, 3, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
      <figcaption>
        {chart.y_label} by {chart.x_label.toLowerCase()}
        {chart.kind === "bar" && chart.points.length === 20 ? " (top 20)" : ""}
      </figcaption>
    </figure>
  );
}
