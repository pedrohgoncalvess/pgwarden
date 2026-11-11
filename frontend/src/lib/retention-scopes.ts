import { apiFetch, authHeaders } from '$lib/auth';
import type { RetentionWindow } from '$lib/retention-api';

export type Scope = 'global' | 'project' | 'server';
export const globalScopeId = '00000000-0000-0000-0000-000000000000';
export type ScopedPolicy = RetentionWindow & {
	scope: Scope;
	scope_id: string;
	table_name: string;
	retention_interval: string;
	enabled: boolean;
};
export type ScopeSettings = {
	tables: string[];
	projects: { id: string; name: string }[];
	servers: {
		id: number;
		public_id: string;
		name: string;
		ingestion_project_id: string | null;
		deleted_at: string | null;
	}[];
	policies: ScopedPolicy[];
	effective: { server_id: string; name: string; policy: ScopedPolicy | null }[];
	runs: { public_id: string; table_name: string; last_run_at: string; deleted_rows: number }[];
};
export type ScopedPreview = {
	window: RetentionWindow;
	expired_rows: number;
	expired_bytes: number;
	logical_bytes: number;
	projected_bytes: number | null;
	affected_tables: number;
	tables: {
		server_id: string;
		server_name: string;
		name: string;
		preserved: boolean;
		current_policy: ScopedPolicy | null;
		expired_rows?: number;
	}[];
};
async function request<T>(path: string, method = 'GET', body?: RetentionWindow): Promise<T> {
	const response = await apiFetch(`/api/v1/retention/scopes${path}`, {
		method,
		headers: authHeaders(),
		cache: 'no-store',
		...(body ? { body: JSON.stringify(body) } : {})
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			typeof error.detail === 'string'
				? error.detail
				: `Retention request failed (${response.status})`
		);
	}
	return response.status === 204 ? (undefined as T) : response.json();
}
const path = (scope: Scope, id: string, table: string) =>
	`/${scope}/${encodeURIComponent(id)}/${encodeURIComponent(table)}`;
export const listScopeSettings = () => request<ScopeSettings>('');
export const previewScope = (scope: Scope, id: string, table: string, window: RetentionWindow) =>
	request<ScopedPreview>(`${path(scope, id, table)}/preview`, 'POST', window);
export const saveScope = (scope: Scope, id: string, table: string, window: RetentionWindow) =>
	request<ScopeSettings>(path(scope, id, table), 'PUT', window);
export const inheritScope = (scope: Scope, id: string, table: string) =>
	request<void>(path(scope, id, table), 'DELETE');
