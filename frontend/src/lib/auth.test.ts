import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('authenticated API requests', () => {
	beforeEach(() => {
		vi.resetModules();
		vi.restoreAllMocks();
	});

	it('clears the token and redirects immediately after a 401 response', async () => {
		const removeItem = vi.fn();
		const replace = vi.fn();
		vi.stubGlobal('localStorage', {
			getItem: vi.fn(() => 'expired-token'),
			removeItem
		});
		vi.stubGlobal('window', {
			location: { pathname: '/overview', replace }
		});
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
		const { apiFetch } = await import('./auth');

		const response = await apiFetch('/api/v1/servers');

		expect(response.status).toBe(401);
		expect(removeItem).toHaveBeenCalledWith('token');
		expect(replace).toHaveBeenCalledWith('/login');
	});
});
