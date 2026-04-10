import { useMemo } from "react";
import type uPlot from "uplot";
import UplotReact from "uplot-react";
import { PerformanceQueryTable } from "@/modules/dashboard/dashboard.performance-query-table";
import {
  buildChartData,
  type TimeRangeFilter,
  useChartContainerWidth,
  usePerformanceStream,
} from "@/modules/dashboard/dashboard.performance-stream";
import "uplot/dist/uPlot.min.css";

type PerformanceChartProps = {
  selectedServerId: string | null;
  selectedServerName: string | null;
  selectedDatabaseId: string | null;
  selectedDatabaseName: string | null;
};

function cssColorFromVar(name: string, fallback: string): string {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  if (!value) {
    return fallback;
  }
  return `hsl(${value})`;
}

export function PerformanceChart({
  selectedServerId,
  selectedServerName,
  selectedDatabaseId,
  selectedDatabaseName,
}: PerformanceChartProps) {
  const { containerRef, chartWidth } = useChartContainerWidth();
  const {
    visiblePoints,
    latestEvent,
    hoverEvent,
    setHoverEvent,
    streamStatus,
    timeRange,
    setTimeRange,
    querySearch,
    setQuerySearch,
    queryCategory,
    setQueryCategory,
    filteredRows,
  } = usePerformanceStream({
    selectedServerId,
    selectedServerName,
    selectedDatabaseId,
    selectedDatabaseName,
  });

  const options = useMemo<uPlot.Options>(
    () => ({
      width: chartWidth,
      height: 300,
      legend: {
        show: true,
        live: true,
      },
      cursor: {
        lock: false,
      },
      series: [
        {},
        {
          label: "Median",
          stroke: cssColorFromVar("--muted-foreground", "hsl(197 10% 68%)"),
          width: 1.5,
          value: (_self, rawValue) => {
            if (rawValue == null) {
              return "--";
            }
            return `${Number(rawValue).toFixed(2)} ms`;
          },
        },
        {
          label: "90th",
          stroke: "hsl(66 55% 56%)",
          width: 1.4,
        },
        {
          label: "95th",
          stroke: "hsl(72 64% 52%)",
          width: 1.4,
        },
        {
          label: "98th",
          stroke: "hsl(78 78% 50%)",
          width: 1.4,
        },
        {
          label: "99th",
          stroke: "hsl(82 92% 47%)",
          width: 1.4,
        },
        {
          label: "Avg I/O",
          stroke: cssColorFromVar("--sf-accent-cyan", "hsl(186 27% 44%)"),
          width: 1.8,
        },
      ],
      scales: {
        x: { time: true },
      },
      axes: [
        { stroke: cssColorFromVar("--border", "hsl(215 40% 22%)") },
        {
          stroke: cssColorFromVar("--border", "hsl(215 40% 22%)"),
          values: (_self, splits) => splits.map((v) => `${v}ms`),
        },
      ],
      grid: {
        stroke: cssColorFromVar("--sf-border-strong", "hsl(188 62% 35%)"),
      },
      hooks: {
        setCursor: [
          (self) => {
            const index = self.cursor.idx;
            if (index == null || index < 0) {
              setHoverEvent(null);
              return;
            }
            const x = self.data[0]?.[index];
            const p95 = self.data[3]?.[index];
            const median = self.data[1]?.[index];
            if (typeof x !== "number" || typeof p95 !== "number" || typeof median !== "number") {
              setHoverEvent(null);
              return;
            }
            setHoverEvent({
              timestamp: x * 1_000,
              p95Ms: p95,
              medianMs: median,
            });
          },
        ],
      },
    }),
    [chartWidth, setHoverEvent]
  );

  const data = useMemo<uPlot.AlignedData>(
    () => buildChartData(visiblePoints) as uPlot.AlignedData,
    [visiblePoints]
  );

  return (
    <section className="sf-panel p-4 content-auto">
      <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(240px,1fr)_auto_minmax(260px,1fr)] lg:items-start">
        <div>
          <h2 className="sf-label text-foreground">Query performance trend</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {selectedServerName && selectedDatabaseName
              ? `${selectedServerName} / ${selectedDatabaseName}`
              : "Select server and database to start stream"}
          </p>
        </div>
        <div className="flex items-center gap-2 lg:justify-center">
          <span className="sf-label">Range</span>
          <select
            className="app-input h-9 w-[140px] py-1"
            value={timeRange}
            onChange={(event) => setTimeRange(event.target.value as TimeRangeFilter)}
          >
            <option value="15m">Last 15m</option>
            <option value="1h">Last 1h</option>
            <option value="24h">Last 24h</option>
          </select>
        </div>
        <div className="min-w-[260px] text-left lg:text-right">
          <span className="sf-label inline-block min-w-[120px] text-center lg:text-right">
            {streamStatus === "live"
              ? "SSE stream live"
              : streamStatus === "connecting"
                ? "Connecting stream"
                : "Stream idle"}
          </span>
          <p className="mt-1 h-4 font-mono text-xs tabular-nums text-muted-foreground">
            {hoverEvent
              ? `Hover ${new Date(hoverEvent.timestamp).toLocaleTimeString()} • p95 ${hoverEvent.p95Ms.toFixed(2)}ms`
              : latestEvent
                ? `Live  ${latestEvent.callsPerSec.toFixed(2)} qps • p95 ${latestEvent.p95Ms.toFixed(2)}ms`
                : "Waiting for samples"}
          </p>
        </div>
      </div>
      <div ref={containerRef} className="overflow-x-auto rounded-md border border-border bg-background/25 p-2">
        {selectedServerId && selectedDatabaseId && visiblePoints.length > 0 ? (
          <UplotReact options={options} data={data} />
        ) : selectedServerId && selectedDatabaseId ? (
          <p className="text-sm text-muted-foreground">Preparing streaming samples...</p>
        ) : (
          <p className="text-sm text-muted-foreground">Pick server/database to start fake SSE stream.</p>
        )}
      </div>
      {latestEvent ? (
        <p className="mt-2 truncate text-xs text-muted-foreground">
          Latest sampled query: <span className="text-foreground">{latestEvent.sampleQuery}</span>
        </p>
      ) : null}

      <PerformanceQueryTable
        rows={filteredRows}
        querySearch={querySearch}
        onQuerySearchChange={setQuerySearch}
        queryCategory={queryCategory}
        onQueryCategoryChange={setQueryCategory}
      />
    </section>
  );
}
