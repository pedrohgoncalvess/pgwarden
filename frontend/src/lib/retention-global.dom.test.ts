import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, unmount, tick } from 'svelte';
import RetentionPage from '../routes/(app)/settings/retention/+page.svelte';

const mocks = vi.hoisted(() => ({
	list: vi.fn(),
	preview: vi.fn(),
	save: vi.fn(),
	singlePreview: vi.fn(),
	singleSave: vi.fn()
}));
vi.mock('$lib/access', async () => {
	const { writable } = await import('svelte/store');
	return { profile: writable({ is_admin: true }) };
});
vi.mock('$lib/retention-api', async (original) => ({
	...(await original<typeof import('./retention-api')>()),
	listRetentionPolicies: mocks.list,
	previewGlobalRetention: mocks.preview,
	saveGlobalRetention: mocks.save,
	previewRetention: mocks.singlePreview,
	saveRetention: mocks.singleSave
}));
const policies = ['cpu', 'ram'].map((name) => ({
	name,
	job_id: 1,
	retention_interval: '90 days',
	retention_seconds: 90 * 86400,
	scheduled: true,
	next_start: null,
	schedule_interval: '1 day',
	last_run_status: null
}));
const table = {
	name: 'cpu',
	window: { value: 90, unit: 'days' },
	current_policy: policies[0],
	current_bytes: 1024,
	projected_bytes: 2048,
	baseline_projected_bytes: 2048,
	policy_delta_bytes: 0,
	footprint_delta_bytes: 1024,
	bytes_per_day: 20,
	reclaimable_bytes: 0,
	eligible_chunks: 0,
	total_chunks: 2,
	compressed_chunks: 1,
	first_sample: null,
	last_sample: null,
	measured_at: '2026-11-01T00:00:00Z',
	confidence: 'limited'
};
const preview = {
	...table,
	name: '__all__',
	current_policy: null,
	tables: policies.map((policy) => ({ ...table, name: policy.name, current_policy: policy }))
};

describe('global retention replication', () => {
	let component: ReturnType<typeof mount>;
	let target: HTMLDivElement;
	beforeEach(() => {
		vi.clearAllMocks();
		target = document.createElement('div');
		document.body.append(target);
		mocks.list.mockResolvedValue(policies);
		mocks.preview.mockResolvedValue(preview);
		mocks.save.mockResolvedValue(policies);
		mocks.singlePreview.mockResolvedValue(table);
	});
	afterEach(async () => {
		if (component) await unmount(component);
		target.remove();
	});
	const saveButton = () =>
		[...target.querySelectorAll('button')].find((button) =>
			button.textContent?.includes('Save retention')
		)!;
	async function openGlobal() {
		component = mount(RetentionPage, { target });
		await vi.waitFor(() => expect(target.querySelector('form')).not.toBeNull());
		target.querySelector<HTMLInputElement>('input[type=checkbox]')!.click();
		await tick();
	}
	async function estimate() {
		target
			.querySelector('form')!
			.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
		await vi.waitFor(() => expect(saveButton().disabled).toBe(false));
	}
	it('previews all tables and replicates the duration with one request', async () => {
		await openGlobal();
		expect(saveButton().disabled).toBe(true);
		await estimate();
		expect(mocks.preview).toHaveBeenCalledWith({ value: 90, unit: 'days' });
		expect(target.textContent).toContain('Impact by table');
		expect(target.textContent).toContain('metric.ram');
		saveButton().click();
		await vi.waitFor(() =>
			expect(target.textContent).toContain('Retention policy saved for all 2 metric tables')
		);
		expect(mocks.save).toHaveBeenCalledWith({ value: 90, unit: 'days' });
		expect(mocks.singleSave).not.toHaveBeenCalled();
	});
	it('invalidates the global preview when switching back to a table', async () => {
		await openGlobal();
		await estimate();
		target.querySelector<HTMLInputElement>('input[type=checkbox]')!.click();
		await tick();
		expect(saveButton().disabled).toBe(true);
		await estimate();
		expect(mocks.singlePreview).toHaveBeenCalledWith('cpu', { value: 90, unit: 'days' });
	});
	it('keeps global failures visible and allows retrying', async () => {
		mocks.save.mockRejectedValueOnce(new Error('Policy update failed'));
		await openGlobal();
		await estimate();
		saveButton().click();
		await vi.waitFor(() =>
			expect(target.querySelector('[role=alert]')?.textContent).toContain('Policy update failed')
		);
		expect(saveButton().disabled).toBe(false);
	});
});
