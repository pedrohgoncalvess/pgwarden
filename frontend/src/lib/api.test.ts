import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
	getAnalyticsData,
	getIndexAnalytics,
	getQueryAnalytics,
	getQueryExecutionHistory,
	listRunHistory
} from './api';

const origin = 'http://localhost';
const jsonResponse = new Response(JSON.stringify([]), {
	status: 200,
	headers: { 'Content-Type': 'application/json' }
});

describe('API URL contracts', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		vi.stubGlobal('window', { location: { origin } });
		vi.stubGlobal('localStorage', { getItem: () => null });
		vi.stubGlobal(
			'fetch',
			vi.fn().mockImplementation(async () => jsonResponse.clone())
		);
	});

	it('defaults every analytics request to the last day', async () => {
		await getAnalyticsData('db');
		await getIndexAnalytics('db');
		await getQueryAnalytics('db');
		await getQueryExecutionHistory('db', 'hash');
		expect(fetch).toHaveBeenCalledTimes(4);
		for (const [url] of vi.mocked(fetch).mock.calls) {
			expect(new URL(String(url)).searchParams.get('preset')).toBe('1d');
		}
	});

	it('preserves explicit date bounds instead of adding a conflicting preset', async () => {
		await getQueryAnalytics('db', {
			startDate: '2026-10-01T00:00:00Z',
			endDate: '2026-10-02T00:00:00Z'
		});
		const url = new URL(String(vi.mocked(fetch).mock.calls[0][0]));
		expect(url.searchParams.has('preset')).toBe(false);
		expect(url.searchParams.get('start_date')).toBe('2026-10-01T00:00:00Z');
	});

	it('sends every run-history filter and ordering option', async () => {
		await listRunHistory('database-id', 50, 10, {
			runType: 'database',
			status: 'failed',
			name: 'collector',
			startedFrom: '2026-07-01T00:00:00Z',
			startedTo: '2026-07-02T00:00:00Z',
			minDurationSeconds: 1.5,
			maxDurationSeconds: 30,
			orderBy: 'duration',
			orderDir: 'asc'
		});

		const fetchMock = vi.mocked(fetch);
		const requestUrl = new URL(String(fetchMock.mock.calls[0][0]), origin);
		expect(Object.fromEntries(requestUrl.searchParams)).toEqual({
			limit: '50',
			offset: '10',
			run_type: 'database',
			status: 'failed',
			name: 'collector',
			started_from: '2026-07-01T00:00:00Z',
			started_to: '2026-07-02T00:00:00Z',
			min_duration_seconds: '1.5',
			max_duration_seconds: '30',
			order_by: 'duration',
			order_dir: 'asc'
		});
	});

	it('sends query ordering and repeated exclusions', async () => {
		await getQueryAnalytics('database-id', {
			preset: '1d',
			exclude: ['vacuum', 'analyze'],
			orderBy: 'total_duration',
			orderDir: 'desc'
		});

		const fetchMock = vi.mocked(fetch);
		const requestUrl = new URL(String(fetchMock.mock.calls[0][0]));
		expect(requestUrl.searchParams.get('order_by')).toBe('total_duration');
		expect(requestUrl.searchParams.get('order_dir')).toBe('desc');
		expect(requestUrl.searchParams.getAll('exclude')).toEqual(['vacuum', 'analyze']);
	});
});
