import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	createProject,
	listProjects,
	listProjectKeys,
	optionalDays,
	keyStatus,
	revokeProjectKey,
	rotateProjectKey,
	updateProject,
	type ProjectKey,
	type ProjectSettings
} from './projects-api';

const settings: ProjectSettings = {
	name: 'Production',
	enabled: true,
	key_expiration_days: null,
	rotation_interval_days: null,
	rotation_grace_hours: 24
};
const key: ProjectKey = {
	id: 'key',
	prefix: 'pgw_prefix',
	created_at: '2026-01-01T00:00:00Z',
	expires_at: null,
	retire_at: null,
	revoked_at: null,
	last_used_at: null
};

describe('project management requests', () => {
	beforeEach(() => {
		vi.stubGlobal('localStorage', { getItem: () => 'administrator-jwt' });
		vi.stubGlobal(
			'fetch',
			vi
				.fn()
				.mockResolvedValue(
					new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
				)
		);
	});
	afterEach(() => vi.unstubAllGlobals());
	it('creates a project preserving opt-out policies', async () => {
		await createProject(settings);
		const [url, request] = vi.mocked(fetch).mock.calls[0];
		expect(url).toBe('/api/v1/projects');
		expect(request?.method).toBe('POST');
		expect(request?.cache).toBe('no-store');
		expect(request?.headers).toMatchObject({ Authorization: 'Bearer administrator-jwt' });
		expect(JSON.parse(String(request?.body))).toEqual(settings);
	});
	it('supports configured expiration and automatic rotation', async () => {
		await updateProject('project', {
			...settings,
			key_expiration_days: 90,
			rotation_interval_days: 30
		});
		expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/projects/project');
		expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toMatchObject({
			key_expiration_days: 90,
			rotation_interval_days: 30
		});
	});
	it('lists projects and keys with authenticated requests', async () => {
		await listProjects();
		vi.mocked(fetch).mockResolvedValueOnce(new Response('[]'));
		await listProjectKeys('project');
		expect(vi.mocked(fetch).mock.calls.map((call) => call[0])).toEqual([
			'/api/v1/projects',
			'/api/v1/projects/project/keys'
		]);
	});
	it('rotates immediately by default and supports explicit overlap', async () => {
		await rotateProjectKey('project');
		vi.mocked(fetch).mockResolvedValueOnce(new Response('{}'));
		await rotateProjectKey('project', 12);
		expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toEqual({ grace_hours: 0 });
		expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body))).toEqual({
			grace_hours: 12
		});
	});
	it('revokes without attempting to decode a 204 response', async () => {
		vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }));
		await expect(revokeProjectKey('project', 'key')).resolves.toBeUndefined();
		expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBe('DELETE');
	});
	it('shows administrator and validation failures as useful errors', async () => {
		vi.mocked(fetch).mockResolvedValueOnce(
			new Response(JSON.stringify({ detail: 'Administrator access required' }), { status: 403 })
		);
		await expect(listProjects()).rejects.toThrow('Administrator access required');
		vi.mocked(fetch).mockResolvedValueOnce(
			new Response(JSON.stringify({ detail: [{ msg: 'invalid' }] }), { status: 422 })
		);
		await expect(createProject(settings)).rejects.toThrow('Project request failed (422)');
	});
});

describe('key policy presentation', () => {
	it('treats empty expiration and rotation inputs as optional', () => {
		expect(optionalDays('')).toBeNull();
		expect(optionalDays('   ')).toBeNull();
		expect(optionalDays('30')).toBe(30);
	});
	it.each(['0', '-1', '1.5', '3651', 'invalid'])('rejects invalid policy input %s', (value) =>
		expect(() => optionalDays(value)).toThrow()
	);
	it('distinguishes active, retiring, retired, expired, and revoked keys', () => {
		const now = Date.parse('2026-02-01T00:00:00Z');
		expect(keyStatus(key, now)).toBe('Active');
		expect(keyStatus({ ...key, retire_at: '2026-03-01T00:00:00Z' }, now)).toBe('Retiring');
		expect(keyStatus({ ...key, retire_at: '2026-01-02T00:00:00Z' }, now)).toBe('Retired');
		expect(keyStatus({ ...key, expires_at: '2026-01-02T00:00:00Z' }, now)).toBe('Expired');
		expect(keyStatus({ ...key, revoked_at: '2026-01-02T00:00:00Z' }, now)).toBe('Revoked');
	});
});
