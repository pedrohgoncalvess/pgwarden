import { apiFetch, authHeaders } from '$lib/auth';

export type ProjectSettings = {
	name: string;
	enabled: boolean;
	key_expiration_days: number | null;
	rotation_interval_days: number | null;
	rotation_grace_hours: number;
};

export type Project = ProjectSettings & {
	id: string;
	created_at: string;
	next_rotation_at: string | null;
	last_event_at: string | null;
};

export type ProjectKey = {
	id: string;
	prefix: string;
	created_at: string;
	expires_at: string | null;
	retire_at: string | null;
	revoked_at: string | null;
	last_used_at: string | null;
};

export type IssuedKey = { key: string; metadata: ProjectKey };
export type ProjectCreated = { project: Project; credential: IssuedKey };

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
	const response = await apiFetch(`/api/v1/projects${path}`, {
		method,
		headers: authHeaders(),
		cache: 'no-store',
		...(body !== undefined ? { body: JSON.stringify(body) } : {})
	});
	if (!response.ok) {
		const result = await response.json().catch(() => ({}));
		throw new Error(
			typeof result.detail === 'string'
				? result.detail
				: `Project request failed (${response.status})`
		);
	}
	return response.status === 204 ? (undefined as T) : response.json();
}

export const listProjects = () => request<Project[]>('');
export const createProject = (settings: ProjectSettings) =>
	request<ProjectCreated>('', 'POST', settings);
export const updateProject = (id: string, settings: ProjectSettings) =>
	request<Project>(`/${encodeURIComponent(id)}`, 'PUT', settings);
export const listProjectKeys = (id: string) =>
	request<ProjectKey[]>(`/${encodeURIComponent(id)}/keys`);
export const rotateProjectKey = (id: string, graceHours = 0) =>
	request<IssuedKey>(`/${encodeURIComponent(id)}/keys/rotate`, 'POST', { grace_hours: graceHours });
export const revokeProjectKey = (projectId: string, keyId: string) =>
	request<void>(`/${encodeURIComponent(projectId)}/keys/${encodeURIComponent(keyId)}`, 'DELETE');

export function optionalDays(value: string): number | null {
	if (!value.trim()) return null;
	const days = Number(value);
	if (!Number.isInteger(days) || days < 1 || days > 3650)
		throw new Error('Days must be a whole number between 1 and 3650.');
	return days;
}

export function keyStatus(key: ProjectKey, now = Date.now()): string {
	if (key.revoked_at) return 'Revoked';
	if (key.expires_at && Date.parse(key.expires_at) <= now) return 'Expired';
	if (key.retire_at) return Date.parse(key.retire_at) <= now ? 'Retired' : 'Retiring';
	return 'Active';
}
