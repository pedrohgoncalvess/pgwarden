import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getColumnUsage, getDatabaseSchemaHistory } from './api';

const origin = 'http://localhost';

describe('schema detail API contracts', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		vi.stubGlobal('window', { location: { origin } });
		vi.stubGlobal('localStorage', { getItem: () => 'token' });
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				new Response(JSON.stringify({ items: [], total: 0, limit: 100, offset: 0 }), {
					status: 200,
					headers: { 'Content-Type': 'application/json' }
				})
			)
		);
	});

	it('requests history scoped to a table and column', async () => {
		await getDatabaseSchemaHistory('database-id', 'table-id', 100, 0, 'column-id');

		const requestUrl = new URL(String(vi.mocked(fetch).mock.calls[0][0]));
		expect(requestUrl.searchParams.get('table_id')).toBe('table-id');
		expect(requestUrl.searchParams.get('column_id')).toBe('column-id');
	});

	it('requests parsed usage for a column', async () => {
		await getColumnUsage('database-id', 'table-id', 'column-id');

		expect(vi.mocked(fetch).mock.calls[0][0]).toBe(
			'/api/v1/databases/database-id/analytics/table-usage/table-id/columns/column-id'
		);
	});
});
