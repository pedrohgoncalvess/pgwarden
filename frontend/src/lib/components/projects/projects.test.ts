import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import ProjectForm from './ProjectForm.svelte';
import ProjectKeys from './ProjectKeys.svelte';
import type { ProjectKey } from '$lib/projects-api';

describe('project settings views', () => {
	it('renders optional expiration and rotation and explains credential handoff', () => {
		const { body } = render(ProjectForm, { props: { onsave: async () => {} } });
		expect(body).toContain('Key lifetime (days, optional)');
		expect(body).toContain('Automatic rotation (days, optional)');
		expect(body).toContain('No expiration');
		expect(body).toContain('Manual only');
		expect(body).toContain('replacement key');
		expect(body).toContain('Create project and key');
	});
	it('shows lifecycle metadata and disabled revocation for revoked keys', () => {
		const key: ProjectKey = {
			id: 'key',
			prefix: 'pgw_visible',
			created_at: '2026-01-01T00:00:00Z',
			expires_at: null,
			retire_at: null,
			revoked_at: '2026-01-02T00:00:00Z',
			last_used_at: null
		};
		const { body } = render(ProjectKeys, {
			props: { keys: [key], busy: false, onrotate: async () => {}, onrevoke: async () => {} }
		});
		expect(body).toContain('pgw_visible');
		expect(body).toContain('Revoked');
		expect(body).toContain('No expiration');
		expect(body).toMatch(/disabled[^>]*>Revoke/);
		expect(body).toContain('Zero overlap invalidates every previous key immediately');
	});
});
