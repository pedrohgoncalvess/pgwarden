/** Convert old bookmarks and notification links to the current menu hierarchy. */
export function canonicalPath(path: string): string {
	if (path === '/servers') return '/settings/servers';
	if (path === '/metadata/search') return '/search';
	if (path === '/metadata/documentation') return '/schema/documentation';
	if (path === '/metadata/tag') return '/schema/tags';
	if (path === '/runs/settings/services' || path === '/settings/services') return '/jobs/services';
	if (path === '/settings/collector') return '/jobs/server';
	if (path === '/settings/runs' || path.startsWith('/settings/runs/'))
		return path.replace('/settings/runs', '/jobs');
	if (path.startsWith('/settings/jobs/')) return path.replace('/settings/jobs/', '/jobs/');
	const serverJob = path.match(/^\/runs(?:\/([^/]+))?\/settings\/server$/);
	if (serverJob) return `/jobs/server${serverJob[1] ? `/${serverJob[1]}` : ''}`;
	const databaseJob = path.match(/^\/runs(?:\/([^/]+))?\/settings\/database$/);
	if (databaseJob) return `/jobs/database${databaseJob[1] ? `/${databaseJob[1]}` : ''}`;
	const collector = path.match(/^\/settings\/collector\/(server|database)(\/[^/]+)?$/);
	if (collector) return `/jobs/${collector[1]}${collector[2] ?? ''}`;
	const documentation = path.match(/^\/metadata\/([^/]+)\/documentation$/);
	if (documentation) return `/schema/${documentation[1]}/documentation`;
	const tags = path.match(/^\/metadata\/([^/]+)\/tag$/);
	if (tags) return `/schema/tags/${tags[1]}`;
	if (path === '/runs' || /^\/runs\/(?:[^/]+\/)?(live|history)$/.test(path))
		return path.replace('/runs', '/jobs');
	return path;
}
