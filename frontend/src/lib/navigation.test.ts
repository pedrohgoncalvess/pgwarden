import { describe, expect, it } from 'vitest';
import {
	contextualHref,
	switchDatabasePath,
	switchServerPath,
	workspaceContext,
	sectionFor
} from './navigation';

describe('workspace navigation', () => {
	it('preserves investigation sections when switching databases', () => {
		for (const [before, after] of [
			['/overview/a', '/overview/b'],
			['/schema/a', '/schema/b'],
			['/analytics/a/deep', '/analytics/b/deep'],
			['/analytics/query', '/analytics/b/query'],
			['/jobs/a/history', '/jobs/b/history'],
			['/jobs/database/a', '/jobs/database/b'],
			['/schema/a/documentation', '/schema/b/documentation']
		])
			expect(switchDatabasePath(before, 'b')).toBe(after);
		expect(switchDatabasePath('/settings/account', 'b')).toBe('/settings/account');
	});
	it('uses server context for tags and server jobs, database context for analytics', () => {
		expect(contextualHref('/schema/tags', 'db', 'server')).toBe('/schema/tags/server');
		expect(contextualHref('/jobs/server', 'db', 'server')).toBe('/jobs/server/server');
		expect(contextualHref('/analytics/query', 'db', 'server')).toBe('/analytics/db/query');
		expect(contextualHref('/analytics/time-travel', null, null)).toBe('/analytics');
	});

	it('groups metadata with schema and executions with Jobs', () => {
		expect(sectionFor('/schema/db/documentation')).toBe('schema');
		expect(sectionFor('/jobs/db/live')).toBe('jobs');
		expect(sectionFor('/activity')).toBe('activity');
	});
	it('keeps server-specific screens when switching context', () => {
		expect(switchServerPath('/settings/connections/a', 'b')).toBe('/settings/connections/b');
		expect(switchServerPath('/schema/tags/a', 'b')).toBe('/schema/tags/b');
		expect(switchServerPath('/jobs/server/a', 'b')).toBe('/jobs/server/b');
		expect(switchServerPath('/activity', 'b')).toBe('/activity');
	});

	it('gives the route priority and never shows a database from a different server', () => {
		const catalog = [
			{ id: 'db-a', server_id: 'a' },
			{ id: 'db-b', server_id: 'b' }
		];
		expect(workspaceContext(catalog, undefined, 'b', 'db-a', 'a')).toEqual({
			serverId: 'b',
			databaseId: null
		});
		expect(workspaceContext(catalog, 'db-b', undefined, 'db-a', 'a')).toEqual({
			serverId: 'b',
			databaseId: 'db-b'
		});
		expect(workspaceContext(catalog, undefined, undefined, 'db-a', null)).toEqual({
			serverId: 'a',
			databaseId: 'db-a'
		});
	});
});
