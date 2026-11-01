import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
	initialWindow,
	formatBytes,
	previewRetention,
	saveRetention,
	retentionUnits,
	type RetentionPolicy
} from './retention-api';
import { canVisit, type Profile } from './access';
import { sectionTabs } from './navigation';

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
vi.mock('$lib/auth', () => ({
	apiFetch: fetchMock,
	authHeaders: () => ({ Authorization: 'Bearer test' })
}));

const policy = (interval: string, seconds: number) =>
	({ retention_interval: interval, retention_seconds: seconds }) as RetentionPolicy;
beforeEach(() => fetchMock.mockReset());

describe('retention editor', () => {
	it('offers all requested units and preserves calendar months', () => {
		expect(retentionUnits).toEqual(['minutes', 'hours', 'days', 'weeks', 'months']);
		expect(initialWindow(policy('1 year', 365 * 86400))).toEqual({ value: 12, unit: 'months' });
		expect(initialWindow(policy('3 mons', 92 * 86400))).toEqual({ value: 3, unit: 'months' });
		expect(initialWindow(policy('90 days', 90 * 86400))).toEqual({ value: 90, unit: 'days' });
		expect(initialWindow(policy('00:15:00', 900))).toEqual({ value: 15, unit: 'minutes' });
	});
	it('distinguishes missing estimates from empty storage and formats decreases', () => {
		expect(formatBytes(null)).toBe('Insufficient data');
		expect(formatBytes(0)).toBe('0 B');
		expect(formatBytes(-2048)).toBe('-2 KiB');
	});
	it('keeps the global Settings submenu restricted to administrators', () => {
		expect(sectionTabs.settings.some((tab) => tab.href === '/settings/retention')).toBe(true);
		const user = { is_admin: false, permissions: [] } as unknown as Profile;
		expect(canVisit(user, '/settings/retention')).toBe(false);
		expect(canVisit({ ...user, is_admin: true }, '/settings/retention')).toBe(true);
	});
	it('previews separately from updating the actual policy', async () => {
		fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
		const window = { value: 2, unit: 'weeks' } as const;
		await previewRetention('cpu', window);
		await saveRetention('cpu', window);
		expect(
			fetchMock.mock.calls.map(([path, options]) => [
				path,
				options.method,
				JSON.parse(options.body)
			])
		).toEqual([
			['/api/v1/retention/cpu/preview', 'POST', window],
			['/api/v1/retention/cpu', 'PUT', window]
		]);
	});
	it('surfaces server errors', async () => {
		fetchMock.mockResolvedValue({
			ok: false,
			status: 503,
			json: async () => ({ detail: 'TimescaleDB unavailable' })
		});
		await expect(previewRetention('cpu', { value: 1, unit: 'days' })).rejects.toThrow(
			'TimescaleDB unavailable'
		);
	});
});
