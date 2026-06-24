type DatabaseListItem = {
  id: string;
  server_id: string;
  name: string;
  status: boolean;
};

type DatabaseStats = {
  database_id: string;
  table_count: number;
  index_count: number;
  view_count: number;
  size_bytes: number | null;
  index_hit_rate: number | null;
};

type UptimeResponse = {
  database_id: string;
  uptime_formatted: string;
  uptime_seconds: number;
  postmaster_start_time: string;
};

export type ServerListItem = {
  id: string;
  name: string;
  status: string;
  databases: { id: string }[];
};

export type ServerCreateInput = {
  name: string;
  host: string;
  port: string;
  username: string;
  password: string;
  ssl_mode: string;
};

export type ServerCreatedResponse = {
  message: string;
  id: string;
};

export type ConnectionTestSuccess = {
  status: 'success';
  version: string;
};

export type ConnectionTestError = {
  status: 'error';
  code: string;
  detail: string;
};

export type DatabaseCreateInput = {
  server_id: string;
  db_name: string;
};

export type SessionMetric = {
  collected_at: string;
  database_id: number;
  pid: number;
  backend_start: string;
  user_name: string | null;
  application_name: string | null;
  client_addr: string | null;
  state: string | null;
  wait_event_type: string | null;
  wait_event: string | null;
  query_start: string | null;
  state_change: string | null;
  query_preview: string | null;
};

export type LockMetric = {
  collected_at: string;
  database_id: number;
  table_id: number;
  holder_pid: number;
  type: string;
  mode: string;
  is_granted: boolean | null;
  query_preview: string | null;
};

export type CpuMetric = {
  collected_at: string;
  server_id: number;
  cpu_percent: number | null;
  cpu_count: number | null;
};

export type RamMetric = {
  collected_at: string;
  server_id: number;
  total_bytes: number | null;
  used_bytes: number | null;
  available_bytes: number | null;
  percent: number | null;
};

function getToken(): string | null {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('token');
  }
  return null;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

export async function listServers(): Promise<ServerListItem[]> {
  const res = await fetch('/api/v1/servers', {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to list servers: ${res.status}`);
  }
  return res.json();
}

export async function testConnection(data: ServerCreateInput): Promise<ConnectionTestSuccess | ConnectionTestError> {
  const res = await fetch('/api/v1/servers/test-connection', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error(`Failed to test connection: ${res.status}`);
  }
  return res.json();
}

export async function createServer(data: ServerCreateInput): Promise<ServerCreatedResponse> {
  const res = await fetch('/api/v1/servers', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error(`Failed to create server: ${res.status}`);
  }
  return res.json();
}

export async function createDatabase(data: DatabaseCreateInput): Promise<{ message: string; id: string }> {
  const res = await fetch('/api/v1/databases', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error(`Failed to create database: ${res.status}`);
  }
  return res.json();
}

export async function deleteDatabase(databaseId: string): Promise<void> {
  const res = await fetch(`/api/v1/databases/${databaseId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to delete database: ${res.status}`);
  }
}

export async function deleteServer(serverId: string): Promise<void> {
  const res = await fetch(`/api/v1/servers/${serverId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Failed to delete server: ${res.status}`);
  }
}

export async function listDatabases(): Promise<DatabaseListItem[]> {
  const res = await fetch('/api/v1/databases', {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to list databases: ${res.status}`);
  }
  return res.json();
}

export async function getDatabaseStats(databaseId: string): Promise<DatabaseStats> {
  const res = await fetch(`/api/v1/databases/${databaseId}/stats`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to get database stats: ${res.status}`);
  }
  return res.json();
}

export async function getDatabaseUptime(databaseId: string): Promise<UptimeResponse> {
  const res = await fetch(`/api/v1/databases/${databaseId}/uptime`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to get database uptime: ${res.status}`);
  }
  return res.json();
}

export function createTpsEventSource(databaseId: string): EventSource {
  const token = getToken();
  const url = new URL(`/api/v1/databases/${databaseId}/metrics/stream`, window.location.origin);
  if (token) {
    url.searchParams.set('token', token);
  }
  return new EventSource(url.toString());
}

function createAuthenticatedEventSource(path: string): EventSource {
  const token = getToken();
  const url = new URL(path, window.location.origin);
  if (token) {
    url.searchParams.set('token', token);
  }
  return new EventSource(url.toString());
}

export function createSessionEventSource(databaseId: string): EventSource {
  return createAuthenticatedEventSource(`/api/v1/databases/${databaseId}/sessions/stream`);
}

export function createLockEventSource(databaseId: string): EventSource {
  return createAuthenticatedEventSource(`/api/v1/databases/${databaseId}/locks/stream`);
}

export function createServerMetricsEventSource(serverId: string): EventSource {
  return createAuthenticatedEventSource(`/api/v1/servers/${serverId}/metrics/stream`);
}

export function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex++;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

export { type DatabaseListItem, type DatabaseStats, type UptimeResponse };
