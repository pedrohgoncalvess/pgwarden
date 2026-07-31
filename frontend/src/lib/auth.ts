export type SessionValidation = 'valid' | 'invalid' | 'unavailable';

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
	if (window.location.pathname === '/login' || redirecting) return;
	redirecting = true;
	window.location.replace('/login');
}

export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	const response = await globalThis.fetch(input, init);
	if (response.status === 401) redirectToLogin();
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
