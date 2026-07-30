import type { IndexAnalyticsItem } from './api';

export type IndexOrderBy =
	| 'index_name'
	| 'table_name'
	| 'index_type'
	| 'size'
	| 'scans'
	| 'hit_rate';
export type IndexOrderDir = 'asc' | 'desc';

function tableName(item: IndexAnalyticsItem): string {
	return item.schema_name === 'public'
		? item.table_name
		: `${item.schema_name}.${item.table_name}`;
}

function compareItems(
	left: IndexAnalyticsItem,
	right: IndexAnalyticsItem,
	orderBy: IndexOrderBy
): number {
	switch (orderBy) {
		case 'index_name':
			return left.index_name.localeCompare(right.index_name);
		case 'table_name':
			return tableName(left).localeCompare(tableName(right));
		case 'index_type':
			return left.index_type.localeCompare(right.index_type);
		case 'scans':
			return (left.latest_scan_qt ?? 0) - (right.latest_scan_qt ?? 0);
		case 'hit_rate':
			return (left.hit_rate ?? 0) - (right.hit_rate ?? 0);
		default:
			return left.latest_size_bytes - right.latest_size_bytes;
	}
}

export function sortIndexItems(
	items: IndexAnalyticsItem[],
	orderBy: IndexOrderBy,
	orderDir: IndexOrderDir
): IndexAnalyticsItem[] {
	return [...items].sort((left, right) => {
		const comparison = compareItems(left, right, orderBy);
		if (comparison === 0) {
			return left.index_name.localeCompare(right.index_name);
		}
		return orderDir === 'asc' ? comparison : -comparison;
	});
}
