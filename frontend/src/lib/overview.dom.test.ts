import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import Overview from '../routes/(app)/overview/[database_id]/+page.svelte';

const mocks = vi.hoisted(() => ({ sources: [] as EventSource[] }));
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ params: { database_id: 'db' } }) };
});
vi.mock('$app/navigation', () => ({ goto: vi.fn() }));
vi.mock('$lib/api', async (original) => {
	const api = await original<typeof import('./api')>();
	const source = () => {
		class Source extends EventTarget {
			onopen: ((event: Event) => void) | null = null;
			onerror: ((event: Event) => void) | null = null;
			close = vi.fn();
			dispatchEvent(event: Event) {
				if (event.type === 'open') this.onopen?.(event);
				if (event.type === 'error') this.onerror?.(event);
				return super.dispatchEvent(event);
			}
		}
		const instance = new Source() as unknown as EventSource;
		mocks.sources.push(instance);
		return instance;
	};
	return {
		...api,
		listDatabases: vi.fn().mockResolvedValue([{ id: 'db', server_id: 'server', name: 'test' }]),
		listServers: vi.fn().mockResolvedValue([]),
		getDatabaseMetricsSummary: vi.fn().mockResolvedValue({ stats: null, uptime: null }),
		getServiceHealth: vi.fn().mockResolvedValue(null),
		createTpsEventSource: source,
		createSessionEventSource: source,
		createNativeQueryEventSource: source,
		createLockEventSource: source,
		createServerMetricsEventSource: source
	};
});

describe('Overview stream status', () => {
	let component: ReturnType<typeof mount>;
	let target: HTMLDivElement;
	beforeEach(async () => {
		mocks.sources.length = 0;
		target = document.createElement('div');
		document.body.append(target);
		component = mount(Overview, { target });
		await vi.waitFor(() => expect(mocks.sources).toHaveLength(5));
		for (const source of mocks.sources) source.dispatchEvent(new Event('open'));
		await tick();
	});
	afterEach(async () => {
		await unmount(component);
		target.remove();
	});

	it('clears a transport failure on reopen without waiting for new metrics', async () => {
		mocks.sources[0].dispatchEvent(new Event('error'));
		await tick();
		expect(target.textContent).toContain('Connection interrupted. Reconnecting');
		mocks.sources[0].dispatchEvent(new Event('open'));
		await tick();
		expect(target.textContent).toContain('LIVE');
		expect(target.textContent).not.toContain('Connection interrupted');
	});

	it('keeps another failed stream visible when only one reconnects', async () => {
		mocks.sources[0].dispatchEvent(new Event('error'));
		mocks.sources[1].dispatchEvent(new Event('error'));
		mocks.sources[0].dispatchEvent(new Event('open'));
		await tick();
		expect(target.textContent).toContain('RECONNECTING');
	});

	it('distinguishes collection errors and recovers on a RAM update without CPU or TPS', async () => {
		const server = mocks.sources[4];
		server.dispatchEvent(new MessageEvent('error', { data: '{"error":"collection failed"}' }));
		await tick();
		expect(target.textContent).toContain('DATA UNAVAILABLE');
		expect(target.textContent).not.toContain('RECONNECTING');
		server.dispatchEvent(new MessageEvent('ram', { data: '{"ram_percent":10}' }));
		await tick();
		expect(target.textContent).toContain('LIVE');
		expect(target.textContent).toContain('Last update');
	});

	it('starts with fresh connection state after hiding and resuming the tab', async () => {
		mocks.sources[0].dispatchEvent(new Event('error'));
		const visibility = vi.spyOn(document, 'visibilityState', 'get');
		try {
			visibility.mockReturnValue('hidden');
			document.dispatchEvent(new Event('visibilitychange'));
			await tick();
			expect(target.textContent).toContain('PAUSED');
			visibility.mockReturnValue('visible');
			document.dispatchEvent(new Event('visibilitychange'));
			await tick();
			expect(mocks.sources).toHaveLength(10);
			expect(target.textContent).not.toContain('RECONNECTING');
			for (const source of mocks.sources.slice(5)) source.dispatchEvent(new Event('open'));
			await tick();
			expect(target.textContent).toContain('LIVE');
		} finally {
			visibility.mockRestore();
		}
	});
});
