type FakeMetricsSseOptions = {
  serverId: string;
  serverName: string;
  databaseId: string;
  databaseName: string;
  intervalMs?: number;
};

export type QueryRowSample = {
  id: string;
  query: string;
  role: string;
  avgMs: number;
  callsPerMin: number;
  ioPercent: number;
  runtimePercent: number;
  category: "select" | "write" | "ddl";
};

export type QueryMetricStreamEvent = {
  timestamp: number;
  serverId: string;
  serverName: string;
  databaseId: string;
  databaseName: string;
  medianMs: number;
  p90Ms: number;
  p95Ms: number;
  p98Ms: number;
  p99Ms: number;
  avgIoMs: number;
  callsPerSec: number;
  activeQueries: number;
  sampleQuery: string;
  topQueries: QueryRowSample[];
};

type FakeEventSourceLike = {
  addEventListener: EventTarget["addEventListener"];
  removeEventListener: EventTarget["removeEventListener"];
  close: () => void;
  readyState: number;
};

const READY_STATE_CONNECTING = 0;
const READY_STATE_CLOSED = 2;
const MAX_QUERY_VARIANTS = 5;
const QUERY_SAMPLES = [
  "SELECT * FROM pg_stat_activity WHERE state = 'active'",
  "SELECT relname, seq_scan, idx_scan FROM pg_stat_user_tables",
  "SELECT query, calls, mean_exec_time FROM pg_stat_statements",
  "SELECT datname, numbackends FROM pg_stat_database",
  "SELECT indexrelname, idx_scan FROM pg_stat_user_indexes",
] as const;
const QUERY_POOL = [
  "SELECT * FROM base.user WHERE email = $1 LIMIT 1",
  "SELECT id, status, inserted_at FROM monitoring.server WHERE deleted_at IS NULL",
  "SELECT id, db_name, status FROM monitoring.database WHERE server_id = $1",
  "WITH recent AS (SELECT * FROM monitoring.query_log ORDER BY occurred_at DESC LIMIT 500) SELECT avg(duration_ms) FROM recent",
  "SELECT schema_name, name FROM monitoring.table WHERE database_id = $1 ORDER BY name",
  "INSERT INTO monitoring.query_log(server_id, database_id, fingerprint, duration_ms) VALUES ($1, $2, $3, $4)",
  "UPDATE monitoring.server SET status = $2 WHERE id = $1",
  "DELETE FROM monitoring.query_log WHERE occurred_at < now() - interval '7 days'",
  "SELECT index_name, index_scans FROM monitoring.index_stats WHERE database_id = $1",
  "SELECT relation_name, dead_tuples FROM monitoring.table_stats WHERE database_id = $1",
  "SELECT wait_event, count(*) FROM pg_stat_activity GROUP BY wait_event",
  "VACUUM ANALYZE base.user",
  "ALTER TABLE monitoring.query_log ADD COLUMN runtime_bucket smallint",
  "SELECT percentile_disc(0.95) WITHIN GROUP (ORDER BY duration_ms) FROM monitoring.query_log WHERE database_id = $1",
] as const;
const ROLES = ["pgweb_workers", "app_rw", "reporting", "etl_sync"] as const;

function hashString(input: string): number {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function jitter(seed: number, factor: number): number {
  return ((seed % 1000) / 1000 - 0.5) * factor;
}

function createMetricPayload(
  options: FakeMetricsSseOptions,
  tick: number,
  baseSeed: number
): QueryMetricStreamEvent {
  const timestamp = Date.now();
  const sinWave = Math.sin((tick + baseSeed % 12) / 6);
  const cosWave = Math.cos((tick + baseSeed % 24) / 9);
  const baseline = 11 + (baseSeed % 11);

  const medianMs = Number((baseline + sinWave * 4 + jitter(baseSeed + tick, 2.4)).toFixed(2));
  const p90Ms = Number((medianMs * 1.2 + 1.6 + Math.max(sinWave, -0.1) * 1.2).toFixed(2));
  const p95Ms = Number((medianMs * 1.35 + 3.8 + Math.max(cosWave, 0) * 2.8).toFixed(2));
  const p98Ms = Number((p95Ms * 1.16 + 1.8).toFixed(2));
  const p99Ms = Number((p98Ms * 1.14 + 1.2).toFixed(2));
  const avgIoMs = Number((Math.max(0.4, medianMs * 0.17 + 0.6 + jitter(baseSeed + tick * 2, 0.8))).toFixed(2));
  const callsPerSec = Number((8 + (baseSeed % 7) + Math.max(sinWave, -0.15) * 5).toFixed(2));
  const activeQueries = Math.max(1, Math.round(2 + (baseSeed % 4) + Math.max(cosWave, -0.4) * 5));
  const queryIndex = (baseSeed + tick) % MAX_QUERY_VARIANTS;
  const rotatingOffset = Math.floor(tick / 3) % QUERY_POOL.length;
  const visibleQueries = Array.from({ length: 8 }, (_, index) => {
    return QUERY_POOL[(rotatingOffset + index) % QUERY_POOL.length] ?? QUERY_POOL[0];
  });

  const topQueries = visibleQueries.map((query, index) => {
    const rowSeed = baseSeed + tick * (index + 2) + rotatingOffset * 11;
    const category = index % 3 === 0 ? "select" : index % 3 === 1 ? "write" : "ddl";
    const avgMs = Number((Math.max(0.3, medianMs * (0.45 + index * 0.18) + jitter(rowSeed, 1.6))).toFixed(2));
    const callsPerMin = Number((Math.max(0.5, callsPerSec * 52 - index * 120 + jitter(rowSeed, 45))).toFixed(2));
    const ioPercent = Number((Math.max(0.02, avgIoMs * (0.25 + index * 0.22))).toFixed(2));
    const runtimePercent = Number((Math.max(0.15, p95Ms * (0.4 + index * 0.14))).toFixed(2));
    return {
      id: `${options.serverId}:${options.databaseId}:${hashString(query)}`,
      query,
      role: ROLES[(rowSeed + index) % ROLES.length] ?? ROLES[0],
      avgMs,
      callsPerMin,
      ioPercent,
      runtimePercent,
      category,
    } satisfies QueryRowSample;
  });

  return {
    timestamp,
    serverId: options.serverId,
    serverName: options.serverName,
    databaseId: options.databaseId,
    databaseName: options.databaseName,
    medianMs,
    p90Ms,
    p95Ms,
    p98Ms,
    p99Ms,
    avgIoMs,
    callsPerSec,
    activeQueries,
    sampleQuery: QUERY_SAMPLES[queryIndex] ?? QUERY_SAMPLES[0],
    topQueries,
  };
}

export function createFakeMetricsEventSource(options: FakeMetricsSseOptions): FakeEventSourceLike {
  const target = new EventTarget();
  const baseSeed = hashString(`${options.serverId}:${options.databaseId}`);
  const intervalMs = options.intervalMs ?? 1200;
  let readyState = READY_STATE_CONNECTING;
  let tick = 0;

  const dispatchOpen = () => {
    if (readyState === READY_STATE_CLOSED) {
      return;
    }
    target.dispatchEvent(new Event("open"));
  };

  const dispatchMessage = () => {
    if (readyState === READY_STATE_CLOSED) {
      return;
    }
    tick += 1;
    const payload = createMetricPayload(options, tick, baseSeed);
    target.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(payload) }));
  };

  const openTimeout = window.setTimeout(dispatchOpen, 50);
  const timer = window.setInterval(dispatchMessage, intervalMs);

  return {
    addEventListener: target.addEventListener.bind(target),
    removeEventListener: target.removeEventListener.bind(target),
    close: () => {
      readyState = READY_STATE_CLOSED;
      window.clearTimeout(openTimeout);
      window.clearInterval(timer);
      target.dispatchEvent(new Event("close"));
    },
    get readyState() {
      return readyState;
    },
  };
}
