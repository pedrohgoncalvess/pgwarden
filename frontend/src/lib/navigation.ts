import { canonicalPath } from './routePaths';

export type Destination = { label: string; href: string; icon: string };

export function contextualHref(
	path: string,
	databaseId: string | null,
	serverId: string | null
): string {
	path = canonicalPath(path);
	if (!databaseId && path === '/analytics/time-travel') return '/analytics';
	if (databaseId && /^\/(overview|schema)$/.test(path)) return `${path}/${databaseId}`;
	if (databaseId && path.startsWith('/analytics/'))
		return path.replace('/analytics/', `/analytics/${databaseId}/`);
	if (databaseId && /^\/jobs\/(live|history)$/.test(path))
		return path.replace('/jobs/', `/jobs/${databaseId}/`);
	if (databaseId && path === '/schema/documentation') return `/schema/${databaseId}/documentation`;
	if (serverId && path === '/schema/tags') return `/schema/tags/${serverId}`;
	if (serverId && path === '/jobs/server') return `/jobs/server/${serverId}`;
	if (databaseId && path === '/jobs/database') return `/jobs/database/${databaseId}`;
	return path;
}

export function sectionFor(path: string): string {
	return canonicalPath(path).split('/')[1] || 'overview';
}

export function tabIsActive(path: string, target: string): boolean {
	return path === target || (target === '/settings/connections' && path.startsWith(`${target}/`));
}

export const destinations: Destination[] = [
	{ label: 'Overview', href: '/overview', icon: 'grid_view' },
	{ label: 'Activity', href: '/activity', icon: 'monitoring' },
	{ label: 'Analytics', href: '/analytics/query', icon: 'bar_chart' },
	{ label: 'Schema', href: '/schema', icon: 'account_tree' },
	{ label: 'Alerts', href: '/alerts/server', icon: 'notifications' },
	{ label: 'Jobs', href: '/jobs/live', icon: 'work_history' },
	{ label: 'Settings', href: '/settings/connections', icon: 'settings' }
];

export const sectionTabs: Record<string, Destination[]> = {
	analytics: [
		{ label: 'Queries', href: '/analytics/query', icon: 'search' },
		{ label: 'Deep analysis', href: '/analytics/deep', icon: 'travel_explore' },
		{ label: 'Data', href: '/analytics/data', icon: 'analytics' },
		{ label: 'Indexes', href: '/analytics/index', icon: 'speed' },
		{ label: 'Recommendations', href: '/analytics/recommendations', icon: 'tips_and_updates' },
		{ label: 'Time travel', href: '/analytics/time-travel', icon: 'history_toggle_off' }
	],
	schema: [
		{ label: 'Structure', href: '/schema', icon: 'account_tree' },
		{ label: 'Documentation', href: '/schema/documentation', icon: 'description' },
		{ label: 'Tags', href: '/schema/tags', icon: 'label' }
	],
	alerts: [
		{ label: 'Server', href: '/alerts/server', icon: 'dns' },
		{ label: 'Database', href: '/alerts/database', icon: 'database' },
		{ label: 'Table', href: '/alerts/table', icon: 'table' },
		{ label: 'Index', href: '/alerts/index', icon: 'speed' },
		{ label: 'Configuration', href: '/alerts/configuration', icon: 'settings' }
	],
	jobs: [
		{ label: 'Live runs', href: '/jobs/live', icon: 'precision_manufacturing' },
		{ label: 'Run history', href: '/jobs/history', icon: 'history' },
		{ label: 'Server jobs', href: '/jobs/server', icon: 'dns' },
		{ label: 'Database jobs', href: '/jobs/database', icon: 'database' },
		{ label: 'Services', href: '/jobs/services', icon: 'hub' }
	],
	settings: [
		{ label: 'Retention', href: '/settings/retention', icon: 'history' },
		{ label: 'Connections', href: '/settings/connections', icon: 'cable' },
		{ label: 'Servers', href: '/settings/servers', icon: 'lan' },
		{ label: 'Projects', href: '/settings/projects', icon: 'key' },
		{ label: 'Users', href: '/settings/users', icon: 'group' },
		{ label: 'Roles', href: '/settings/roles', icon: 'shield_person' },
		{ label: 'Change password', href: '/settings/password', icon: 'lock' },
		{ label: 'Account', href: '/settings/account', icon: 'manage_accounts' }
	]
};

export function switchDatabasePath(path: string, databaseId: string): string {
	path = canonicalPath(path);
	if (
		/^\/(overview|schema)(\/[^/]+)?$/.test(path) &&
		!path.startsWith('/schema/tags') &&
		path !== '/schema/documentation'
	)
		return `/${path.split('/')[1]}/${databaseId}`;
	if (path === '/schema/documentation' || /^\/schema\/[^/]+\/documentation$/.test(path))
		return `/schema/${databaseId}/documentation`;
	if (path.startsWith('/analytics/')) return `/analytics/${databaseId}/${path.split('/').at(-1)}`;
	if (/^\/jobs\/(?:[^/]+\/)?(live|history)$/.test(path))
		return `/jobs/${databaseId}/${path.split('/').at(-1)}`;
	if (/^\/jobs\/database(?:\/[^/]+)?$/.test(path)) return `/jobs/database/${databaseId}`;
	return path;
}

export function switchServerPath(path: string, serverId: string): string {
	path = canonicalPath(path);
	if (/^\/settings\/connections\/[^/]+$/.test(path)) return `/settings/connections/${serverId}`;
	if (/^\/schema\/tags(?:\/[^/]+)?$/.test(path)) return `/schema/tags/${serverId}`;
	if (/^\/jobs\/server(?:\/[^/]+)?$/.test(path)) return `/jobs/server/${serverId}`;
	return path;
}

export function workspaceContext(
	databases: { id: string; server_id: string }[],
	routeDatabase: string | undefined,
	routeServer: string | undefined,
	selectedDatabase: string | null,
	selectedServer: string | null
) {
	const selected = databases.find((db) => db.id === selectedDatabase);
	const serverId =
		routeServer ??
		databases.find((db) => db.id === routeDatabase)?.server_id ??
		selectedServer ??
		selected?.server_id ??
		null;
	const databaseId = routeDatabase ?? (selected?.server_id === serverId ? selected.id : null);
	return { serverId, databaseId };
}
