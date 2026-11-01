import { describe, expect, it, vi } from 'vitest';
import { createCatalogCache } from './catalogCache';

describe('shared catalog requests', () => {
	it('deduplicates concurrent reads and gives each consumer a readable response', async () => {
		const cache = createCatalogCache();
		const load = vi.fn(async () => Response.json([{ id: 'db' }]));
		const responses = await Promise.all([
			cache.read('databases', 'user', load),
			cache.read('databases', 'user', load)
		]);
		expect(load).toHaveBeenCalledTimes(1);
		expect(await Promise.all(responses.map((response) => response.json()))).toEqual([
			[{ id: 'db' }],
			[{ id: 'db' }]
		]);
		await cache.read('databases', 'user', load);
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('does not reuse data across sessions, after invalidation, or after expiry', async () => {
		vi.useFakeTimers();
		try {
			const cache = createCatalogCache(100);
			const load = vi.fn(async () => Response.json([]));
			await cache.read('servers', 'first-user', load);
			await cache.read('servers', 'second-user', load);
			cache.clear();
			await cache.read('servers', 'second-user', load);
			vi.advanceTimersByTime(101);
			await cache.read('servers', 'second-user', load);
			expect(load).toHaveBeenCalledTimes(4);
		} finally {
			vi.useRealTimers();
		}
	});

	it('does not cache failed requests', async () => {
		const cache = createCatalogCache();
		const load = vi
			.fn()
			.mockResolvedValueOnce(new Response(null, { status: 500 }))
			.mockResolvedValueOnce(Response.json([]));
		await cache.read('servers', 'user', load);
		expect((await cache.read('servers', 'user', load)).ok).toBe(true);
		expect(load).toHaveBeenCalledTimes(2);
	});

	it('prevents a request started before a mutation from repopulating the cache', async () => {
		const cache = createCatalogCache();
		let finish!: (response: Response) => void;
		const pending = cache.read(
			'servers',
			'user',
			() =>
				new Promise((resolve) => {
					finish = resolve;
				})
		);
		cache.clear();
		finish(Response.json(['old']));
		await pending;
		expect(
			await (await cache.read('servers', 'user', async () => Response.json(['new']))).json()
		).toEqual(['new']);
	});
});
