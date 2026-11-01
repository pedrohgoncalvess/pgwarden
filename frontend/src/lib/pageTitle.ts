import { canonicalPath } from './routePaths';

const PAGE_TITLES: Record<string, string> = {
	'': 'Home',
	login: 'Login',
	search: 'Search',
	overview: 'Overview',
	activity: 'Activity',
	schema: 'Schema',
	'settings/servers': 'Servers',
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
	jobs: 'Jobs',
	'jobs/live': 'Live Runs',
	'jobs/history': 'Run History',
	'jobs/server': 'Server Run Settings',
	'jobs/database': 'Database Run Settings',
	'schema/documentation': 'Metadata Documentation',
	'schema/tags': 'Metadata Tags',
	'settings/account': 'Account Settings',
	'settings/retention': 'Data Retention',
	'settings/access': 'Users',
	'settings/users': 'Users',
	'settings/roles': 'Roles',
	'settings/password': 'Change Password',
	'settings/projects': 'Projects & Ingestion',
	'settings/connections': 'Connection Settings',
	'jobs/services': 'Services'
};

function routeKey(pathname: string): string {
	const segments = canonicalPath(pathname).split('/').filter(Boolean);
	const primary = segments[0];
	if (primary === 'overview') return primary;
	if (primary === 'schema') {
		if (segments.at(-1) === 'documentation') return 'schema/documentation';
		if (segments[1] === 'tags') return 'schema/tags';
		return 'schema';
	}
	if (primary === 'analytics' && segments.length >= 3) return `analytics/${segments.at(-1)}`;
	if (primary === 'jobs') {
		if (['live', 'history'].includes(segments.at(-1) ?? '')) return `jobs/${segments.at(-1)}`;
		return segments.slice(0, 2).join('/');
	}
	if (primary === 'settings') return segments.slice(0, 2).join('/');
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
