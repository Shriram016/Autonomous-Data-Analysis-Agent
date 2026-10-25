// Number formats by unit: the SAME rules as the backend's format_number (agent/facts.py), so
// the chart's axis and tooltip read exactly like the table. If one side changes, change both
// (the tests below and in backend/tests/unit/test_facts.py pin the same examples).
import type { Chart } from "./api";

export type Unit = Chart["unit"]; // "count" | "BRL" | "ratio" | "days" | "score"

const grouped = (value: number, decimals: number) =>
  value.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

export function formatNumber(value: number, unit: Unit): string {
  switch (unit) {
    case "count":
      return grouped(Math.trunc(value), 0); // 96,478
    case "BRL":
      return `R$ ${grouped(value, 2)}`; // R$ 2,136,258.96
    case "ratio":
      return `${(value * 100).toFixed(2)}%`; // 6.77%
    case "days":
      return `${value.toFixed(1)} days`; // 12.5 days
    case "score":
      return value.toFixed(2); // 4.09
  }
}

/** A short form for the chart's axis ticks, where space is tight: R$ 2.1M, 6.8%, 12 days. */
export function formatAxis(value: number, unit: Unit): string {
  const compact = (n: number) =>
    n.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 });
  switch (unit) {
    case "BRL":
      return `R$ ${compact(value)}`;
    case "ratio":
      return `${(value * 100).toFixed(1)}%`;
    case "days":
      return `${Math.round(value)} d`;
    default:
      return compact(value);
  }
}
