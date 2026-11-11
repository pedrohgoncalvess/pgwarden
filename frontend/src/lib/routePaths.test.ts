import { describe, expect, it } from 'vitest';
import { canonicalPath } from './routePaths';
import { sectionTabs, contextualHref, tabIsActive } from './navigation';
import { getPageTitle } from './pageTitle';

describe('menu route hierarchy', () => {
	it.each([
		['/settings/runs', '/jobs'],
		['/settings/runs/live', '/jobs/live'],
		['/settings/runs/history', '/jobs/history'],
		['/settings/runs/db/live', '/jobs/db/live'],
		['/settings/runs/db/history', '/jobs/db/history'],
		['/settings/jobs/server', '/jobs/server'],
		['/settings/jobs/database', '/jobs/database'],
		['/settings/jobs/server/server', '/jobs/server/server'],
		['/settings/jobs/database/db', '/jobs/database/db'],
		['/settings/services', '/jobs/services'],
		['/runs', '/jobs'],
		['/runs/live', '/jobs/live'],
		['/runs/history', '/jobs/history'],
		['/runs/db/live', '/jobs/db/live'],
		['/runs/db/history', '/jobs/db/history'],
		['/runs/settings/server', '/jobs/server'],
		['/runs/settings/database', '/jobs/database'],
		['/runs/server/settings/server', '/jobs/server/server'],
		['/runs/db/settings/database', '/jobs/database/db'],
		['/runs/settings/services', '/jobs/services'],
		['/servers', '/settings/servers'],
		['/metadata/search', '/search'],
		['/metadata/documentation', '/schema/documentation'],
		['/metadata/db/documentation', '/schema/db/documentation'],
		['/metadata/tag', '/schema/tags'],
		['/metadata/server/tag', '/schema/tags/server'],
		['/settings/collector', '/jobs/server'],
		['/settings/collector/server', '/jobs/server'],
		['/settings/collector/database', '/jobs/database'],
		['/settings/collector/server/server', '/jobs/server/server'],
		['/settings/collector/database/db', '/jobs/database/db']
	])('redirects %s to %s without another redirect', (before, after) => {
		expect(canonicalPath(before)).toBe(after);
		expect(canonicalPath(after)).toBe(after);
	});

	it('keeps every tab under its sidebar section, including contextual links and icons', () => {
		for (const [section, tabs] of Object.entries(sectionTabs)) {
			for (const tab of tabs) {
				expect(tab.href.startsWith(`/${section}`)).toBe(true);
				expect(contextualHref(tab.href, 'db', 'server').startsWith(`/${section}/`)).toBe(true);
				expect(tab.icon).toBeTruthy();
			}
		}
	});

	it('does not select the Structure tab while reading documentation', () => {
		expect(tabIsActive('/schema/db/documentation', '/schema/db')).toBe(false);
		expect(tabIsActive('/schema/db/documentation', '/schema/db/documentation')).toBe(true);
		expect(tabIsActive('/settings/connections/server', '/settings/connections')).toBe(true);
	});

	it('keeps descriptive page titles after moving contextual pages', () => {
		expect(getPageTitle('/jobs/db/history')).toBe('Run History | PGWarden');
		expect(getPageTitle('/jobs/server/server')).toBe('Server Run Settings | PGWarden');
		expect(getPageTitle('/schema/db/documentation')).toBe('Metadata Documentation | PGWarden');
		expect(getPageTitle('/schema/tags/server')).toBe('Metadata Tags | PGWarden');
	});

	it('preserves unrelated application and API paths', () => {
		expect(canonicalPath('/alerts/database')).toBe('/alerts/database');
		expect(canonicalPath('/api/v1/databases/db/runs/history')).toBe(
			'/api/v1/databases/db/runs/history'
		);
	});
});
