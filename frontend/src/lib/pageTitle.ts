const PAGE_TITLES: Record<string, string> = {
	'': 'Home',
	login: 'Login',
	search: 'Search',
	overview: 'Overview',
	schema: 'Schema',
	servers: 'Servers',
	alerts: 'Alerts',
	'alerts/server': 'Server Alerts',
	'alerts/database': 'Database Alerts',
	'alerts/table': 'Table Alerts',
	'alerts/index': 'Index Alerts',
	'alerts/configuration': 'Alert Configuration',
	analytics: 'Analytics',
	'analytics/data': 'Data Analytics',
	'analytics/query': 'Query Analytics',
	'analytics/index': 'Index Analytics',
	runs: 'Runs',
	'runs/live': 'Live Runs',
	'runs/history': 'Run History',
	'runs/settings/server': 'Server Run Settings',
	'runs/settings/database': 'Database Run Settings',
	'metadata/search': 'Metadata Search',
	'metadata/documentation': 'Metadata Documentation',
	'metadata/tag': 'Metadata Tags',
	'settings/account': 'Account Settings',
	'settings/connections': 'Connection Settings',
	'settings/collector': 'Collector Settings',
	'settings/collector/server': 'Server Collector Settings',
	'settings/collector/database': 'Database Collector Settings'
};

function routeKey(pathname: string): string {
	const segments = pathname.split('/').filter(Boolean);
	const primary = segments[0];

	if (primary === 'overview' || primary === 'schema') {
		return primary;
	}

	if ((primary === 'analytics' || primary === 'metadata') && segments.length >= 3) {
		return `${primary}/${segments.at(-1)}`;
	}

	if (primary === 'runs' && segments[1] && !['live', 'history', 'settings'].includes(segments[1])) {
		segments.splice(1, 1);
	}

	if (primary === 'settings' && segments[1] === 'connections') {
		return 'settings/connections';
	}

	if (
		primary === 'settings' &&
		segments[1] === 'collector' &&
		['server', 'database'].includes(segments[2])
	) {
		return segments.slice(0, 3).join('/');
	}

	return segments.join('/');
}

function fallbackTitle(pathname: string): string {
	const segment = pathname.split('/').filter(Boolean).at(-1);
	if (!segment) return 'Home';
	return segment
		.replaceAll('-', ' ')
		.replaceAll('_', ' ')
		.replace(/\b\w/g, (character) => character.toUpperCase());
}

export function getPageTitle(pathname: string): string {
	const title = PAGE_TITLES[routeKey(pathname)] ?? fallbackTitle(pathname);
	return title === 'Home' || title === 'Login' ? 'PGWarden' : `${title} | PGWarden`;
}
