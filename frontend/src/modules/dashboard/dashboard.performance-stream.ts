import { useEffect, useMemo, useRef, useState } from "react";
import {
  createFakeMetricsEventSource,
  type QueryMetricStreamEvent,
  type QueryRowSample,
} from "@/modules/dashboard/dashboard.metrics-sse";

export type ChartPoint = {
  timestamp: number;
  medianMs: number;
  p90Ms: number;
  p95Ms: number;
  p98Ms: number;
  p99Ms: number;
  avgIoMs: number;
};

export type StreamStatus = "idle" | "connecting" | "live";
export type QueryCategoryFilter = "all" | "select" | "write" | "ddl";
export type TimeRangeFilter = "15m" | "1h" | "24h";

export type HoverSnapshot = {
  timestamp: number;
  p95Ms: number;
  medianMs: number;
};

type StreamContext = {
  selectedServerId: string | null;
  selectedServerName: string | null;
  selectedDatabaseId: string | null;
  selectedDatabaseName: string | null;
};

export function useChartContainerWidth() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [chartWidth, setChartWidth] = useState(980);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }
    const node = containerRef.current;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 980;
      setChartWidth(Math.max(680, Math.floor(width - 8)));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return { containerRef, chartWidth };
}

export function usePerformanceStream(context: StreamContext) {
  const { selectedServerId, selectedServerName, selectedDatabaseId, selectedDatabaseName } = context;
  const [points, setPoints] = useState<ChartPoint[]>([]);
  const [latestEvent, setLatestEvent] = useState<QueryMetricStreamEvent | null>(null);
  const [hoverEvent, setHoverEvent] = useState<HoverSnapshot | null>(null);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("idle");
  const [timeRange, setTimeRange] = useState<TimeRangeFilter>("24h");
  const [querySearch, setQuerySearch] = useState("");
  const [queryCategory, setQueryCategory] = useState<QueryCategoryFilter>("all");

  useEffect(() => {
    if (!selectedServerId || !selectedDatabaseId || !selectedServerName || !selectedDatabaseName) {
      setPoints([]);
      setLatestEvent(null);
      setHoverEvent(null);
      setStreamStatus("idle");
      return;
    }

    const stream = createFakeMetricsEventSource({
      serverId: selectedServerId,
      serverName: selectedServerName,
      databaseId: selectedDatabaseId,
      databaseName: selectedDatabaseName,
    });
    setStreamStatus("connecting");

    const rawPoints: ChartPoint[] = [];

    const handleOpen = () => {
      setStreamStatus("live");
    };

    const handleMessage = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as QueryMetricStreamEvent;
      setLatestEvent(payload);
      rawPoints.push({
        timestamp: payload.timestamp,
        medianMs: payload.medianMs,
        p90Ms: payload.p90Ms,
        p95Ms: payload.p95Ms,
        p98Ms: payload.p98Ms,
        p99Ms: payload.p99Ms,
        avgIoMs: payload.avgIoMs,
      });
      if (rawPoints.length > 480) {
        rawPoints.shift();
      }
      setPoints([...rawPoints]);
    };

    stream.addEventListener("open", handleOpen);
    stream.addEventListener("message", handleMessage as unknown as EventListener);

    return () => {
      stream.removeEventListener("open", handleOpen);
      stream.removeEventListener("message", handleMessage as unknown as EventListener);
      stream.close();
    };
  }, [selectedDatabaseId, selectedDatabaseName, selectedServerId, selectedServerName]);

  const visiblePoints = useMemo(() => {
    const secondsWindow = timeRange === "15m" ? 900 : timeRange === "1h" ? 3600 : 24 * 3600;
    const now = Date.now();
    return points.filter((point) => point.timestamp >= now - secondsWindow * 1_000);
  }, [points, timeRange]);

  const filteredRows = useMemo(() => {
    const rows = latestEvent?.topQueries ?? [];
    return rows.filter((row) => {
      const byCategory = queryCategory === "all" ? true : row.category === queryCategory;
      if (!byCategory) {
        return false;
      }
      const q = querySearch.trim().toLowerCase();
      if (!q) {
        return true;
      }
      return row.query.toLowerCase().includes(q) || row.role.toLowerCase().includes(q);
    });
  }, [latestEvent?.topQueries, queryCategory, querySearch]);

  return {
    points,
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
  };
}

export function formatPct(value: number) {
  return `${value.toFixed(2)}%`;
}

export function formatMs(value: number) {
  return `${value.toFixed(2)}ms`;
}

export function buildChartData(points: ChartPoint[]) {
  const x = points.map((p) => p.timestamp / 1_000);
  const median = points.map((p) => p.medianMs);
  const p90 = points.map((p) => p.p90Ms);
  const p95 = points.map((p) => p.p95Ms);
  const p98 = points.map((p) => p.p98Ms);
  const p99 = points.map((p) => p.p99Ms);
  const avgIo = points.map((p) => p.avgIoMs);
  return [x, median, p90, p95, p98, p99, avgIo];
}

export function filterRows(
  rows: QueryRowSample[],
  queryCategory: QueryCategoryFilter,
  querySearch: string
) {
  return rows.filter((row) => {
    const byCategory = queryCategory === "all" ? true : row.category === queryCategory;
    if (!byCategory) {
      return false;
    }
    const q = querySearch.trim().toLowerCase();
    if (!q) {
      return true;
    }
    return row.query.toLowerCase().includes(q) || row.role.toLowerCase().includes(q);
  });
}
