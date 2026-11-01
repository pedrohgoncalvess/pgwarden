import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, unmount, tick } from 'svelte';
import RetentionPage from '../routes/(app)/settings/retention/+page.svelte';

const mocks = vi.hoisted(() => ({ list: vi.fn(), preview: vi.fn(), save: vi.fn() }));
vi.mock('$lib/access', async () => {
	const { writable } = await import('svelte/store');
	return { profile: writable({ is_admin: true }) };
});
vi.mock('$lib/retention-api', async (original) => ({
	...(await original<typeof import('./retention-api')>()),
	listRetentionPolicies: mocks.list,
	previewRetention: mocks.preview,
	saveRetention: mocks.save
}));

const policy = {
	name: 'cpu',
	job_id: 42,
	retention_interval: '90 days',
	retention_seconds: 90 * 86400,
	scheduled: true,
	next_start: null,
	schedule_interval: '1 day',
	last_run_status: null
};
const preview = {
	name: 'cpu',
	window: { value: 90, unit: 'days' },
	current_policy: policy,
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

describe('retention settings interaction', () => {
	let component: ReturnType<typeof mount>;
	let target: HTMLDivElement;
	beforeEach(() => {
		vi.clearAllMocks();
		target = document.createElement('div');
		document.body.append(target);
		mocks.list.mockResolvedValue([policy]);
		mocks.preview.mockResolvedValue(preview);
		mocks.save.mockResolvedValue(policy);
	});
	afterEach(async () => {
		if (component) await unmount(component);
		target.remove();
	});
	const saveButton = () =>
		[...target.querySelectorAll('button')].find((button) =>
			button.textContent?.includes('Save retention')
		)!;
	async function open() {
		component = mount(RetentionPage, { target });
		await vi.waitFor(() => expect(target.querySelector('form')).not.toBeNull());
	}
	async function simulate() {
		target
			.querySelector('form')!
			.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
		await vi.waitFor(() => expect(saveButton().disabled).toBe(false));
	}
	it('requires a preview, invalidates edited durations, then saves the selected policy', async () => {
		await open();
		expect(saveButton().disabled).toBe(true);
		await simulate();
		expect(mocks.preview).toHaveBeenCalledWith('cpu', { value: 90, unit: 'days' });
		const input = target.querySelector<HTMLInputElement>('input')!;
		input.value = '30';
		input.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
		expect(saveButton().disabled).toBe(true);
		expect(target.textContent).toContain('Estimate again');
		mocks.preview.mockResolvedValue({ ...preview, window: { value: 30, unit: 'days' } });
		await simulate();
		saveButton().click();
		await vi.waitFor(() => expect(target.textContent).toContain('Retention policy saved'));
		expect(mocks.save).toHaveBeenCalledWith('cpu', { value: 30, unit: 'days' });
		expect(saveButton().disabled).toBe(true);
	});
	it('shows estimation failures and keeps saving disabled', async () => {
		mocks.preview.mockRejectedValue(new Error('Storage metadata unavailable'));
		await open();
		target
			.querySelector('form')!
			.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
		await vi.waitFor(() =>
			expect(target.querySelector('[role=alert]')?.textContent).toContain(
				'Storage metadata unavailable'
			)
		);
		expect(saveButton().disabled).toBe(true);
		expect(mocks.save).not.toHaveBeenCalled();
	});
	it('reports missing hypertables', async () => {
		mocks.list.mockResolvedValue([]);
		component = mount(RetentionPage, { target });
		await vi.waitFor(() => expect(target.textContent).toContain('No metric hypertables'));
		expect(target.querySelector('form')).toBeNull();
	});
});
