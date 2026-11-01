import { createCatalogCache } from './catalogCache';

export type SessionValidation = 'valid' | 'invalid' | 'unavailable';

const catalogCache = createCatalogCache();

export function invalidateCatalog(): void {
    catalogCache.clear();
    if (typeof window !== 'undefined')
        window.dispatchEvent?.(new Event('pgwarden:catalog-invalidated'));
}

let redirecting = false;

export function getAccessToken(): string | null {
	if (typeof localStorage === 'undefined') return null;
	return localStorage.getItem('token');
}

export function authHeaders(): Record<string, string> {
	const token = getAccessToken();
	return {
		'Content-Type': 'application/json',
		...(token ? { Authorization: `Bearer ${token}` } : {})
	};
}

export function redirectToLogin(): void {
	if (typeof window === 'undefined') return;
	localStorage.removeItem('token');
	catalogCache.clear();
	if (window.location.pathname === '/login' || redirecting) return;
	redirecting = true;
	window.location.replace('/login');
}

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
	const url = String(input);
	const catalog = /^\/api\/v1\/(servers|databases)\/?$/.test(url);
	const load = () => globalThis.fetch(input, init);
	const response =
		typeof window !== 'undefined' && catalog && method === 'GET' && !init?.signal
			? await catalogCache.read(url, getAccessToken(), load)
			: await load();
	if (response.status === 401) redirectToLogin();
	if (response.ok && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
		catalogCache.clear();
		if (typeof window !== 'undefined')
			window.dispatchEvent?.(new Event('pgwarden:catalog-invalidated'));
	}
	return response;
}

export async function validateSession(): Promise<SessionValidation> {
	if (!getAccessToken()) {
		redirectToLogin();
		return 'invalid';
	}

	try {
		const response = await apiFetch('/api/v1/auth/validate', {
			headers: authHeaders(),
			cache: 'no-store'
		});
		if (response.status === 401) return 'invalid';
		return response.ok ? 'valid' : 'unavailable';
	} catch {
		return 'unavailable';
	}
}
