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

type DatabaseMetricsSummary = {
	database_id: string;
	stats: DatabaseStats;
	uptime: UptimeResponse;
};

export type SchemaColumn = {
	id: string;
	name: string;
	description: string | null;
	data_type: string;
	is_nullable: boolean;
	default_value: string | null;
	is_unique: boolean;
	ordinal_position: number;
	fk_table_id: string | null;
	fk_column_id: string | null;
};

export type SchemaIndex = {
	id: string;
	name: string;
	type: string;
	definition: string;
	is_unique: boolean;
	is_primary: boolean;
	columns: string[];
};

export type SchemaTable = {
	id: string;
	schema_name: string;
	name: string;
	description: string | null;
	columns: SchemaColumn[];
	indexes: SchemaIndex[];
};

export type DatabaseSchema = {
	id: string;
	tables: SchemaTable[];
};

export type SchemaHistoryAction = 'added' | 'removed' | 'altered';
export type SchemaHistoryType = 'table' | 'column' | 'index';

export type SchemaHistoryItem = {
	id: string;
	type: SchemaHistoryType;
	action: SchemaHistoryAction;
	schema_name: string | null;
	table_name: string | null;
	column_name: string | null;
	index_name: string | null;
	object_id: string | null;
	table_id: string | null;
	changed_at: string;
	changed_by: number | null;
	details: string | null;
};

export type SchemaHistoryResponse = {
	total: number;
	limit: number;
	offset: number;
	items: SchemaHistoryItem[];
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

export type NativeQueryMetric = {
	collected_at: string;
	database_id: number;
	pid: number;
	leader_pid: number | null;
	usesysid: number | null;
	user_name: string | null;
	application_name: string | null;
	client_addr: string | null;
	client_hostname: string | null;
	client_port: number | null;
	backend_start: string;
	xact_start: string | null;
	query_start: string | null;
	state_change: string | null;
	wait_event_type: string | null;
	wait_event: string | null;
	state: string | null;
	backend_xid: string | null;
	backend_xmin: string | null;
	query_id: number | null;
	backend_type: string | null;
	query: string | null;
	query_hash: string | null;
	query_duration_ms: number | null;
	transaction_duration_ms: number | null;
	backend_duration_ms: number | null;
};

export type RunType = 'server' | 'database';
export type RunStatus = 'idle' | 'running' | 'paused' | 'deleted';
export type RunAction = 'pause' | 'resume' | 'stop' | 'delete' | 'force_run';

export type RunItem = {
	id: number;
	server_id: number;
	database_id: number | null;
	database_name: string | null;
	name: string;
	type: RunType;
	interval: number;
	is_paused: boolean;
	next_run_at: string | null;
	status: RunStatus;
	action?: RunAction;
};

export type RunHistoryItem = {
	id: number;
	config_id: number | null;
	database_id: number | null;
	database_name: string | null;
	name: string | null;
	type: RunType | null;
	status: string;
	errors: string[];
	started_at: string | null;
	finished_at: string | null;
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
		'Content-Type': 'application/json'
	};
	if (token) {
		headers['Authorization'] = `Bearer ${token}`;
	}
	return headers;
}

export async function listServers(): Promise<ServerListItem[]> {
	const res = await fetch('/api/v1/servers', {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to list servers: ${res.status}`);
	}
	return res.json();
}

export async function testConnection(
	data: ServerCreateInput
): Promise<ConnectionTestSuccess | ConnectionTestError> {
	const res = await fetch('/api/v1/servers/test-connection', {
		method: 'POST',
		headers: authHeaders(),
		body: JSON.stringify(data)
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
		body: JSON.stringify(data)
	});
	if (!res.ok) {
		throw new Error(`Failed to create server: ${res.status}`);
	}
	return res.json();
}

export async function createDatabase(
	data: DatabaseCreateInput
): Promise<{ message: string; id: string }> {
	const res = await fetch('/api/v1/databases', {
		method: 'POST',
		headers: authHeaders(),
		body: JSON.stringify(data)
	});
	if (!res.ok) {
		throw new Error(`Failed to create database: ${res.status}`);
	}
	return res.json();
}

export async function deleteDatabase(databaseId: string): Promise<void> {
	const res = await fetch(`/api/v1/databases/${databaseId}`, {
		method: 'DELETE',
		headers: authHeaders()
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to delete database: ${res.status}`);
	}
}

export async function deleteServer(serverId: string): Promise<void> {
	const res = await fetch(`/api/v1/servers/${serverId}`, {
		method: 'DELETE',
		headers: authHeaders()
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to delete server: ${res.status}`);
	}
}

export type ServerConfigItem = {
	id: number;
	name: string;
	interval: number;
	is_paused: boolean;
};

export type DatabaseConfigItem = {
	id: number;
	name: string;
	interval: number;
	is_paused: boolean;
};

export type ServerConfigPatch = {
	is_paused?: boolean;
	interval?: number;
};

export type DatabaseConfigPatch = {
	is_paused?: boolean;
	interval?: number;
};

export async function listServerConfigs(serverId: string): Promise<ServerConfigItem[]> {
	const res = await fetch(`/api/v1/servers/${serverId}/configs`, {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to list server configs: ${res.status}`);
	}
	return res.json();
}

export async function patchServerConfig(
	serverId: string,
	configId: number,
	patch: ServerConfigPatch
): Promise<ServerConfigItem> {
	const res = await fetch(`/api/v1/servers/${serverId}/configs/${configId}`, {
		method: 'PATCH',
		headers: authHeaders(),
		body: JSON.stringify(patch)
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to update server config: ${res.status}`);
	}
	return res.json();
}

export async function listDatabaseConfigs(databaseId: string): Promise<DatabaseConfigItem[]> {
	const res = await fetch(`/api/v1/databases/${databaseId}/configs`, {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to list database configs: ${res.status}`);
	}
	return res.json();
}

export async function patchDatabaseConfig(
	databaseId: string,
	configId: number,
	patch: DatabaseConfigPatch
): Promise<DatabaseConfigItem> {
	const res = await fetch(`/api/v1/databases/${databaseId}/configs/${configId}`, {
		method: 'PATCH',
		headers: authHeaders(),
		body: JSON.stringify(patch)
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to update database config: ${res.status}`);
	}
	return res.json();
}

export async function listDatabases(): Promise<DatabaseListItem[]> {
	const res = await fetch('/api/v1/databases', {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to list databases: ${res.status}`);
	}
	return res.json();
}

export async function getDatabaseStats(databaseId: string): Promise<DatabaseStats> {
	const res = await fetch(`/api/v1/databases/${databaseId}/metrics/stats`, {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to get database stats: ${res.status}`);
	}
	return res.json();
}

export async function getDatabaseUptime(databaseId: string): Promise<UptimeResponse> {
	const res = await fetch(`/api/v1/databases/${databaseId}/metrics/uptime`, {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to get database uptime: ${res.status}`);
	}
	return res.json();
}

export async function getDatabaseMetricsSummary(databaseId: string): Promise<DatabaseMetricsSummary> {
	const res = await fetch(`/api/v1/databases/${databaseId}/metrics/summary`, {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to get database metrics summary: ${res.status}`);
	}
	return res.json();
}

export async function getDatabaseSchema(databaseId: string): Promise<DatabaseSchema> {
	const res = await fetch(`/api/v1/databases/${databaseId}/schemas`, {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to get database schema: ${res.status}`);
	}
	return res.json();
}

export type DocumentationTargetType = 'database' | 'schema' | 'table' | 'column' | 'index';

export type DocumentationBase = {
	description: string | null;
	tags?: TagItem[];
	created_at?: string;
	updated_at?: string | null;
};

export type DatabaseDocumentation = DocumentationBase & {
	owner: string | null;
	classification: string | null;
};

export type SchemaDocumentation = DatabaseDocumentation;
export type TableDocumentation = DatabaseDocumentation;

export type ColumnDocumentation = DocumentationBase & {
	is_pii: boolean;
	sample_values: string | null;
};

export type IndexDocumentation = DocumentationBase;

export type DocumentationPayload =
	| Partial<DatabaseDocumentation>
	| Partial<ColumnDocumentation>
	| Partial<IndexDocumentation>;

async function readOptionalJson<T>(res: Response, fallbackMessage: string): Promise<T | null> {
	if (res.status === 404) return null;
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `${fallbackMessage}: ${res.status}`);
	}
	return res.json();
}

async function writeJson<T>(url: string, data: unknown, fallbackMessage: string): Promise<T> {
	const res = await fetch(url, {
		method: 'PUT',
		headers: authHeaders(),
		body: JSON.stringify(data)
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `${fallbackMessage}: ${res.status}`);
	}
	return res.json();
}

export async function getDatabaseDocumentation(
	databaseId: string
): Promise<DatabaseDocumentation | null> {
	const res = await fetch(`/api/v1/databases/${databaseId}/docs`, {
		headers: authHeaders()
	});
	return readOptionalJson<DatabaseDocumentation>(res, 'Failed to get database documentation');
}

export async function putDatabaseDocumentation(
	databaseId: string,
	data: Partial<DatabaseDocumentation>
): Promise<DatabaseDocumentation> {
	return writeJson<DatabaseDocumentation>(
		`/api/v1/databases/${databaseId}/docs`,
		data,
		'Failed to save database documentation'
	);
}

export async function getSchemaDocumentation(
	databaseId: string,
	schemaName: string
): Promise<SchemaDocumentation | null> {
	const res = await fetch(
		`/api/v1/databases/${databaseId}/docs/schemas/${encodeURIComponent(schemaName)}`,
		{ headers: authHeaders() }
	);
	return readOptionalJson<SchemaDocumentation>(res, 'Failed to get schema documentation');
}

export async function putSchemaDocumentation(
	databaseId: string,
	schemaName: string,
	data: Partial<SchemaDocumentation>
): Promise<SchemaDocumentation> {
	return writeJson<SchemaDocumentation>(
		`/api/v1/databases/${databaseId}/docs/schemas/${encodeURIComponent(schemaName)}`,
		data,
		'Failed to save schema documentation'
	);
}

export async function getTableDocumentation(
	databaseId: string,
	tableId: string
): Promise<TableDocumentation | null> {
	const res = await fetch(`/api/v1/databases/${databaseId}/docs/tables/${tableId}`, {
		headers: authHeaders()
	});
	return readOptionalJson<TableDocumentation>(res, 'Failed to get table documentation');
}

export async function putTableDocumentation(
	databaseId: string,
	tableId: string,
	data: Partial<TableDocumentation>
): Promise<TableDocumentation> {
	return writeJson<TableDocumentation>(
		`/api/v1/databases/${databaseId}/docs/tables/${tableId}`,
		data,
		'Failed to save table documentation'
	);
}

export async function getColumnDocumentation(
	databaseId: string,
	columnId: string
): Promise<ColumnDocumentation | null> {
	const res = await fetch(`/api/v1/databases/${databaseId}/docs/columns/${columnId}`, {
		headers: authHeaders()
	});
	return readOptionalJson<ColumnDocumentation>(res, 'Failed to get column documentation');
}

export async function putColumnDocumentation(
	databaseId: string,
	columnId: string,
	data: Partial<ColumnDocumentation>
): Promise<ColumnDocumentation> {
	return writeJson<ColumnDocumentation>(
		`/api/v1/databases/${databaseId}/docs/columns/${columnId}`,
		data,
		'Failed to save column documentation'
	);
}

export async function getIndexDocumentation(
	databaseId: string,
	indexId: string
): Promise<IndexDocumentation | null> {
	const res = await fetch(`/api/v1/databases/${databaseId}/docs/indexes/${indexId}`, {
		headers: authHeaders()
	});
	return readOptionalJson<IndexDocumentation>(res, 'Failed to get index documentation');
}

export async function putIndexDocumentation(
	databaseId: string,
	indexId: string,
	data: Partial<IndexDocumentation>
): Promise<IndexDocumentation> {
	return writeJson<IndexDocumentation>(
		`/api/v1/databases/${databaseId}/docs/indexes/${indexId}`,
		data,
		'Failed to save index documentation'
	);
}

export async function getDatabaseSchemaHistory(
	databaseId: string,
	tableId?: string,
	limit = 100,
	offset = 0
): Promise<SchemaHistoryResponse> {
	const url = new URL(`/api/v1/databases/${databaseId}/schemas/history`, window.location.origin);
	url.searchParams.set('limit', String(limit));
	url.searchParams.set('offset', String(offset));
	if (tableId) {
		url.searchParams.set('table_id', tableId);
	}
	const res = await fetch(url.toString(), {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to get schema history: ${res.status}`);
	}
	return res.json();
}

export async function listNativeQueries(
	databaseId: string,
	limit = 100
): Promise<NativeQueryMetric[]> {
	const res = await fetch(`/api/v1/databases/${databaseId}/native-queries?limit=${limit}`, {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to list native queries: ${res.status}`);
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

export function createNativeQueryEventSource(databaseId: string): EventSource {
	return createAuthenticatedEventSource(`/api/v1/databases/${databaseId}/native-queries/stream`);
}

export function createRunEventSource(databaseId: string): EventSource {
	return createAuthenticatedEventSource(`/api/v1/databases/${databaseId}/runs/stream`);
}

export async function listRunHistory(
	databaseId: string,
	limit = 100,
	offset = 0
): Promise<RunHistoryItem[]> {
	const res = await fetch(
		`/api/v1/databases/${databaseId}/runs/history?limit=${limit}&offset=${offset}`,
		{
			headers: authHeaders()
		}
	);
	if (!res.ok) {
		throw new Error(`Failed to list run history: ${res.status}`);
	}
	return res.json();
}

export async function controlRun(
	databaseId: string,
	runId: number,
	_runType: RunType,
	action: RunAction
): Promise<RunItem> {
	const res = await fetch(`/api/v1/databases/${databaseId}/runs/${runId}`, {
		method: 'PATCH',
		headers: authHeaders(),
		body: JSON.stringify({ action })
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to control run: ${res.status}`);
	}
	return res.json();
}
export type AnalyticsTableFilterItem = {
	id: number;
	schema_name: string;
	name: string;
};

export type AnalyticsDatabaseSizePoint = {
	collected_at: string;
	size_bytes: number;
};

export type AnalyticsTableSizePoint = {
	collected_at: string;
	table_id: number;
	schema_name: string;
	table_name: string;
	size_bytes: number;
};

export type AnalyticsDataResponse = {
	database_id: string;
	database_name: string;
	database_size_history: AnalyticsDatabaseSizePoint[];
	table_size_history: AnalyticsTableSizePoint[];
	tables: AnalyticsTableFilterItem[];
};

export type AnalyticsPreset = '1d' | '3d' | '1w' | '2w' | '1m' | 'custom';

export type QueryAnalyticsBreakdownItem = {
	user_name?: string;
	application_name?: string;
	execution_count: number;
};

export type QueryAnalyticsItem = {
	query_signature: string;
	query_preview: string;
	query_hash: string | null;
	execution_count: number;
	avg_duration_ms: number | null;
	max_duration_ms: number | null;
	min_duration_ms: number | null;
	total_duration_ms: number | null;
	unique_users: number;
	user_breakdown: QueryAnalyticsBreakdownItem[];
	unique_applications: number;
	application_breakdown: QueryAnalyticsBreakdownItem[];
	first_seen: string;
	last_seen: string;
};

export type QueryAnalyticsTimelinePoint = {
	timestamp: string;
	execution_count: number;
	avg_duration_ms: number | null;
};

export type QueryAnalyticsFilters = {
	users: (string | null)[];
	applications: (string | null)[];
	states: (string | null)[];
};

export type QueryAnalyticsResponse = {
	database_id: string;
	database_name: string;
	start_at: string;
	end_at: string;
	items: QueryAnalyticsItem[];
	total: number;
	timeline: QueryAnalyticsTimelinePoint[];
	filters: QueryAnalyticsFilters;
};

export type IndexAnalyticsFilterItem = {
	id: number;
	table_id: number;
	schema_name: string;
	table_name: string;
	index_name: string;
	index_type: string;
	is_unique: boolean;
	is_primary: boolean;
};

export type IndexAnalyticsTableFilterItem = {
	id: number;
	schema_name: string;
	name: string;
};

export type IndexAnalyticsMetricPoint = {
	collected_at: string;
	index_id: number;
	size_bytes: number;
	scan_qt: number | null;
	tup_read_qt: number | null;
	tup_fetch_qt: number | null;
	blks_read: number | null;
	blks_hit: number | null;
};

export type IndexAnalyticsKpi = {
	total_indexes: number;
	total_size_bytes: number;
	avg_hit_rate: number | null;
	avg_scan_qt: number | null;
	unused_indexes: number;
	unique_indexes: number;
	primary_indexes: number;
};

export type IndexAnalyticsTimelinePoint = {
	collected_at: string;
	total_size_bytes: number;
	total_scans: number;
	avg_hit_rate: number | null;
};

export type IndexAnalyticsItem = {
	index_id: number;
	table_id: number;
	schema_name: string;
	table_name: string;
	index_name: string;
	index_type: string;
	is_unique: boolean;
	is_primary: boolean;
	latest_size_bytes: number;
	latest_scan_qt: number | null;
	latest_tup_read_qt: number | null;
	latest_tup_fetch_qt: number | null;
	latest_blks_read: number | null;
	latest_blks_hit: number | null;
	hit_rate: number | null;
	total_scans: number | null;
	first_seen: string | null;
	last_seen: string | null;
	history: IndexAnalyticsMetricPoint[];
};

export type IndexAnalyticsResponse = {
	database_id: string;
	database_name: string;
	start_at: string;
	end_at: string;
	kpis: IndexAnalyticsKpi;
	timeline: IndexAnalyticsTimelinePoint[];
	items: IndexAnalyticsItem[];
	tables: IndexAnalyticsTableFilterItem[];
	indexes: IndexAnalyticsFilterItem[];
};

export type TagItem = {
	id: string;
	name: string;
	description: string | null;
	color: string | null;
	type: string;
	created_at: string;
};

export type TagInput = {
	server_id: string;
	name: string;
	description?: string | null;
	color?: string | null;
	type?: string;
};

export type TagAssignmentScope = 'object' | 'doc';
export type TagAssignmentTargetType =
	| 'database'
	| 'schema'
	| 'table'
	| 'column'
	| 'index'
	| 'native_query';

export type TagAssignmentInput = {
	scope: TagAssignmentScope;
	target_type: TagAssignmentTargetType;
	target_id?: string | null;
	database_id?: string | null;
	schema_name?: string | null;
	query_hash?: string | null;
};

export type TagAssignment = TagAssignmentInput & {
	tag: TagItem;
	target_label: string;
	created_at: string;
};

export async function listTags(serverId?: string): Promise<TagItem[]> {
	const url = new URL('/api/v1/tags', window.location.origin);
	if (serverId) {
		url.searchParams.set('server_id', serverId);
	}
	const res = await fetch(url.toString(), {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to list tags: ${res.status}`);
	}
	return res.json();
}

export async function createTag(data: TagInput): Promise<TagItem> {
	const res = await fetch('/api/v1/tags', {
		method: 'POST',
		headers: authHeaders(),
		body: JSON.stringify(data)
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to create tag: ${res.status}`);
	}
	return res.json();
}

export async function updateTag(
	tagId: string,
	data: Partial<Omit<TagInput, 'server_id'>>
): Promise<TagItem> {
	const res = await fetch(`/api/v1/tags/${tagId}`, {
		method: 'PATCH',
		headers: authHeaders(),
		body: JSON.stringify(data)
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to update tag: ${res.status}`);
	}
	return res.json();
}

export async function deleteTag(tagId: string): Promise<void> {
	const res = await fetch(`/api/v1/tags/${tagId}`, {
		method: 'DELETE',
		headers: authHeaders()
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to delete tag: ${res.status}`);
	}
}

export async function listTagAssignments(databaseId?: string): Promise<TagAssignment[]> {
	const url = new URL('/api/v1/tags/assignments', window.location.origin);
	if (databaseId) {
		url.searchParams.set('database_id', databaseId);
	}
	const res = await fetch(url.toString(), {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to list tag assignments: ${res.status}`);
	}
	return res.json();
}

export async function attachTagAssignment(tagId: string, data: TagAssignmentInput): Promise<void> {
	const res = await fetch(`/api/v1/tags/${tagId}/assignments`, {
		method: 'POST',
		headers: authHeaders(),
		body: JSON.stringify(data)
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to attach tag: ${res.status}`);
	}
}

export async function detachTagAssignment(tagId: string, data: TagAssignmentInput): Promise<void> {
	const res = await fetch(`/api/v1/tags/${tagId}/assignments`, {
		method: 'DELETE',
		headers: authHeaders(),
		body: JSON.stringify(data)
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to detach tag: ${res.status}`);
	}
}

export async function getAnalyticsData(
	databaseId: string,
	options: {
		preset?: AnalyticsPreset;
		startDate?: string;
		endDate?: string;
		tableIds?: number[];
	} = {}
): Promise<AnalyticsDataResponse> {
	const url = new URL(`/api/v1/databases/${databaseId}/analytics/data`, window.location.origin);
	if (options.preset && options.preset !== 'custom') {
		url.searchParams.set('preset', options.preset);
	}
	if (options.startDate) {
		url.searchParams.set('start_date', options.startDate);
	}
	if (options.endDate) {
		url.searchParams.set('end_date', options.endDate);
	}
	if (options.tableIds && options.tableIds.length > 0) {
		options.tableIds.forEach((id) => url.searchParams.append('table_ids', String(id)));
	}
	const res = await fetch(url.toString(), {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to get analytics data: ${res.status}`);
	}
	return res.json();
}

export async function getQueryAnalytics(
	databaseId: string,
	options: {
		preset?: AnalyticsPreset;
		startDate?: string;
		endDate?: string;
		userName?: string;
		applicationName?: string;
		state?: string;
		search?: string;
		exclude?: string[];
		limit?: number;
	} = {}
): Promise<QueryAnalyticsResponse> {
	const url = new URL(`/api/v1/databases/${databaseId}/analytics/query`, window.location.origin);
	if (options.preset && options.preset !== 'custom') {
		url.searchParams.set('preset', options.preset);
	}
	if (options.startDate) {
		url.searchParams.set('start_date', options.startDate);
	}
	if (options.endDate) {
		url.searchParams.set('end_date', options.endDate);
	}
	if (options.userName) {
		url.searchParams.set('user_name', options.userName);
	}
	if (options.applicationName) {
		url.searchParams.set('application_name', options.applicationName);
	}
	if (options.state) {
		url.searchParams.set('state', options.state);
	}
	if (options.search) {
		url.searchParams.set('search', options.search);
	}
	if (options.exclude && options.exclude.length > 0) {
		for (const term of options.exclude) {
			url.searchParams.append('exclude', term);
		}
	}
	if (options.limit !== undefined) {
		url.searchParams.set('limit', String(options.limit));
	}
	const res = await fetch(url.toString(), {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to get query analytics: ${res.status}`);
	}
	return res.json();
}

export async function getIndexAnalytics(
	databaseId: string,
	options: {
		preset?: AnalyticsPreset;
		startDate?: string;
		endDate?: string;
		tableIds?: number[];
		indexIds?: number[];
		search?: string;
	} = {}
): Promise<IndexAnalyticsResponse> {
	const url = new URL(`/api/v1/databases/${databaseId}/analytics/index`, window.location.origin);
	if (options.preset && options.preset !== 'custom') {
		url.searchParams.set('preset', options.preset);
	}
	if (options.startDate) {
		url.searchParams.set('start_date', options.startDate);
	}
	if (options.endDate) {
		url.searchParams.set('end_date', options.endDate);
	}
	if (options.tableIds && options.tableIds.length > 0) {
		options.tableIds.forEach((id) => url.searchParams.append('table_ids', String(id)));
	}
	if (options.indexIds && options.indexIds.length > 0) {
		options.indexIds.forEach((id) => url.searchParams.append('index_ids', String(id)));
	}
	if (options.search) {
		url.searchParams.set('search', options.search);
	}
	const res = await fetch(url.toString(), {
		headers: authHeaders()
	});
	if (!res.ok) {
		throw new Error(`Failed to get index analytics: ${res.status}`);
	}
	return res.json();
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

export function formatNumber(n: number | null | undefined): string {
	if (n === null || n === undefined) return '--';
	return n.toLocaleString();
}

export { type DatabaseListItem, type DatabaseStats, type DatabaseMetricsSummary, type UptimeResponse };
