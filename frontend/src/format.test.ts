import { describe, expect, it } from "vitest";

import { formatAxis, formatNumber } from "./format";

// The same examples as the backend's test_each_unit_has_one_format (tests/unit/test_facts.py),
// so the chart and the table can never show the same number two ways.
describe("formatNumber matches the backend's table format", () => {
  it.each([
    [96478, "count", "96,478"],
    [5067633.16, "BRL", "R$ 5,067,633.16"],
    [0.0677, "ratio", "6.77%"],
    [12.4968, "days", "12.5 days"],
    [4.0864, "score", "4.09"],
  ] as const)("%s %s -> %s", (value, unit, shown) => {
    expect(formatNumber(value, unit)).toBe(shown);
  });
});

describe("formatAxis is short", () => {
  it("compacts money and keeps the unit", () => {
    expect(formatAxis(2136258.96, "BRL")).toBe("R$ 2.1M");
    expect(formatAxis(0.0677, "ratio")).toBe("6.8%");
  });
});
