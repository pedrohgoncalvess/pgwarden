import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getQueryAnalytics, getQueryContext, getQueryExecutionHistory } from './api';

describe('Deep Analysis request cancellation', () => {
	beforeEach(() => {
		vi.stubGlobal('window', { location: { origin: 'http://localhost' } });
		vi.stubGlobal('localStorage', { getItem: () => null });
		vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{}')));
	});

	afterEach(() => vi.unstubAllGlobals());

	it('passes cancellation to the query list, history and context requests', async () => {
		const controller = new AbortController();
		await getQueryAnalytics('db', { signal: controller.signal });
		await getQueryExecutionHistory('db', 'hash', { signal: controller.signal });
		await getQueryContext('db', 'hash', '2026-11-01T00:00:00Z', controller.signal);
		for (const [, options] of vi.mocked(fetch).mock.calls) {
			expect(options?.signal).toBe(controller.signal);
		}
	});

	it('propagates cancellation so the page can discard obsolete context requests', async () => {
		vi.mocked(fetch).mockImplementation(
			(_url, options) =>
				new Promise((_resolve, reject) => {
					options?.signal?.addEventListener('abort', () =>
						reject(new DOMException('Aborted', 'AbortError'))
					);
				})
		);
		const controller = new AbortController();
		const request = getQueryContext('db', 'hash', '2026-11-01T00:00:00Z', controller.signal);
		controller.abort();
		await expect(request).rejects.toMatchObject({ name: 'AbortError' });
	});

	it('preserves the custom history interval with cancellation enabled', async () => {
		const controller = new AbortController();
		await getQueryExecutionHistory('db', 'hash', {
			preset: 'custom',
			startDate: '2026-10-01T00:00:00Z',
			endDate: '2026-11-01T00:00:00Z',
			signal: controller.signal
		});
		const url = new URL(String(vi.mocked(fetch).mock.calls[0][0]));
		expect(url.searchParams.get('start_date')).toBe('2026-10-01T00:00:00Z');
		expect(url.searchParams.get('end_date')).toBe('2026-11-01T00:00:00Z');
		expect(url.searchParams.has('preset')).toBe(false);
	});
});
