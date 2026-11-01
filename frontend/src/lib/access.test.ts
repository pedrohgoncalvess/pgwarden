import { describe, expect, it } from 'vitest';
import { can, canVisit, type Profile } from './access';

const reader: Profile = {
	id: 1,
	name: 'Reader',
	email: 'reader@example.com',
	is_admin: false,
	role_id: 1,
	permissions: ['alerts.read', 'documentation.read', 'schedulers.read']
};

describe('role capabilities', () => {
	it('keeps read and configure independent for each feature', () => {
		for (const feature of ['alerts', 'documentation', 'schedulers']) {
			expect(can(reader, `${feature}.read`)).toBe(true);
			expect(can(reader, `${feature}.configure`)).toBe(false);
			const configureOnly = { ...reader, permissions: [`${feature}.configure`] };
			expect(can(configureOnly, `${feature}.read`)).toBe(false);
			expect(can(configureOnly, `${feature}.configure`)).toBe(true);
		}
	});
	it('limits user and role management to administrators', () => {
		expect(canVisit(reader, '/settings/access')).toBe(false);
		expect(canVisit({ ...reader, is_admin: true }, '/settings/access')).toBe(true);
	});
	it('requires scheduler access for the jobs area', () => {
		expect(canVisit(reader, '/jobs/live')).toBe(true);
		expect(canVisit({ ...reader, permissions: [] }, '/jobs/live')).toBe(false);
		expect(canVisit(null, '/jobs/live')).toBe(false);
	});
});
