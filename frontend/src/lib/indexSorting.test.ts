import { describe, expect, it } from 'vitest';

import type { IndexAnalyticsItem } from './api';
import { sortIndexItems, type IndexOrderBy } from './indexSorting';

function item(
	indexName: string,
	overrides: Partial<IndexAnalyticsItem> = {}
): IndexAnalyticsItem {
	return {
		index_id: 1,
		table_id: 1,
		schema_name: 'public',
		table_name: 'table',
		index_name: indexName,
		index_type: 'btree',
		is_unique: false,
		is_primary: false,
		latest_size_bytes: 0,
		latest_scan_qt: 0,
		latest_tup_read_qt: null,
		latest_tup_fetch_qt: null,
		latest_blks_read: null,
		latest_blks_hit: null,
		hit_rate: null,
		total_scans: null,
		first_seen: null,
		last_seen: null,
		history: [],
		...overrides
	};
}

describe('index analytics sorting', () => {
	it.each<[IndexOrderBy, Partial<IndexAnalyticsItem>]>([
		['index_name', { index_name: 'z_index' }],
		['table_name', { table_name: 'z_table' }],
		['index_type', { index_type: 'hash' }],
		['size', { latest_size_bytes: 100 }],
		['scans', { latest_scan_qt: 100 }],
		['hit_rate', { hit_rate: 0.99 }]
	])('sorts descending by %s', (orderBy, leadingValues) => {
		const low = item('a_index');
		const high = item('z_index', leadingValues);

		expect(sortIndexItems([low, high], orderBy, 'desc')[0]).toBe(high);
		expect(sortIndexItems([low, high], orderBy, 'asc')[0]).toBe(low);
	});
});
