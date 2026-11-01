import { get, writable } from 'svelte/store';
import { apiFetch, authHeaders, invalidateCatalog } from './auth';

export type Profile = {
	id: number;
	name: string;
	email: string;
	is_admin: boolean;
	role_id: number | null;
	permissions: string[];
	project_ids?: string[];
	server_ids?: string[];
	database_ids?: string[];
};
export const profile = writable<Profile | null>(null);
export function can(user: Profile | null, permission: string): boolean {
	return !!user && (user.is_admin || user.permissions.includes(permission));
}
export async function loadProfile(): Promise<Profile> {
	const response = await apiFetch('/api/v1/auth/me', { headers: authHeaders(), cache: 'no-store' });
	if (!response.ok) throw new Error('Could not load account permissions');
	const user: Profile = await response.json();
	const previous = get(profile);
	profile.set(user);
	if (previous && JSON.stringify(previous) !== JSON.stringify(user)) invalidateCatalog();
	return user;
}
export function canVisit(user: Profile | null, path: string): boolean {
	if (!user) return false;
	if (user.is_admin) return true;
	if (/^\/settings\/(access|users|roles|connections|retention)/.test(path)) return false;
	if (path.startsWith('/alerts')) return can(user, 'alerts.read');
	if (path.startsWith('/jobs')) return can(user, 'schedulers.read');
	if (path === '/search' || /\/documentation$/.test(path) || path.startsWith('/schema/tags'))
		return can(user, 'documentation.read');
	if (/^\/settings\/(jobs|runs|services)/.test(path)) return can(user, 'schedulers.read');
	return true;
}
export type Role = {
	id: number;
	name: string;
	permissions: string[];
	project_ids: string[];
	server_ids: string[];
	database_ids: string[];
};
export type ManagedUser = Omit<Profile, 'permissions'>;
export async function accessApi<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
	const response = await apiFetch(`/api/v1/access/${path}`, {
		method,
		headers: authHeaders(),
		body: body === undefined ? undefined : JSON.stringify(body)
	});
	if (!response.ok) {
		const error = await response.json().catch(() => ({}));
		throw new Error(
			typeof error.detail === 'string' ? error.detail : `Request failed (${response.status})`
		);
	}
	return response.status === 204 ? (undefined as T) : response.json();
}
