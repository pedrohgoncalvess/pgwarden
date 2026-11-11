import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, unmount, tick } from 'svelte';
import ScopedRetention from './components/retention/ScopedRetention.svelte';
import type { ScopeSettings } from './retention-scopes';

const mocks = vi.hoisted(() => ({
	list: vi.fn(),
	preview: vi.fn(),
	save: vi.fn(),
	inherit: vi.fn()
}));
vi.mock('$lib/retention-scopes', async (original) => ({
	...(await original<typeof import('./retention-scopes')>()),
	listScopeSettings: mocks.list,
	previewScope: mocks.preview,
	saveScope: mocks.save,
	inheritScope: mocks.inherit
}));
const server = '11111111-1111-1111-1111-111111111111';
const project = '22222222-2222-2222-2222-222222222222';
const settings: ScopeSettings = {
	tables: ['cpu'],
	servers: [
		{ id: 1, public_id: server, name: 'Primary', ingestion_project_id: project, deleted_at: null }
	],
	projects: [{ id: project, name: 'Project A' }],
	policies: [
		{
			scope: 'server',
			scope_id: server,
			table_name: '*',
			value: 30,
			unit: 'days',
			retention_interval: '30 days',
			enabled: true
		}
	],
	effective: [
		{
			server_id: server,
			name: 'cpu',
			policy: {
				scope: 'project',
				scope_id: project,
				table_name: '*',
				value: 90,
				unit: 'days',
				retention_interval: '90 days',
				enabled: true
			}
		}
	],
	runs: []
};
describe('scoped retention controls', () => {
	let component: ReturnType<typeof mount>;
	let target: HTMLDivElement;
	beforeEach(() => {
		vi.clearAllMocks();
		target = document.createElement('div');
		document.body.append(target);
		mocks.list.mockResolvedValue(settings);
		mocks.save.mockResolvedValue(settings);
		mocks.inherit.mockResolvedValue(undefined);
		mocks.preview.mockResolvedValue({
			window: { value: 30, unit: 'days' },
			expired_rows: 4,
			expired_bytes: 400,
			logical_bytes: 1000,
			projected_bytes: 1500,
			affected_tables: 1,
			tables: [{ preserved: false }]
		});
	});
	afterEach(async () => {
		if (component) await unmount(component);
		target.remove();
	});
	const button = (text: string) =>
		[...target.querySelectorAll('button')].find((item) => item.textContent?.includes(text))!;
	async function open() {
		component = mount(ScopedRetention, { target });
		await vi.waitFor(() => expect(target.querySelector('form')).not.toBeNull());
	}
	it('requires a fresh scoped preview and sends the selected server identifier', async () => {
		await open();
		expect(button('Save scoped retention').disabled).toBe(true);
		target
			.querySelector('form')!
			.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
		await vi.waitFor(() => expect(button('Save scoped retention').disabled).toBe(false));
		expect(mocks.preview).toHaveBeenCalledWith('server', server, '*', { value: 30, unit: 'days' });
		expect(target.textContent).toContain('4 rows are eligible');
		const input = target.querySelector('input')!;
		input.value = '7';
		input.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
		expect(button('Save scoped retention').disabled).toBe(true);
		input.value = '30';
		input.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
		button('Save scoped retention').click();
		await vi.waitFor(() =>
			expect(mocks.save).toHaveBeenCalledWith('server', server, '*', { value: 30, unit: 'days' })
		);
	});
	it('removes an override to restore inheritance', async () => {
		await open();
		button('Use inherited policy').click();
		await vi.waitFor(() => expect(mocks.inherit).toHaveBeenCalledWith('server', server, '*'));
		await vi.waitFor(() =>
			expect(target.textContent).toContain('inherited policy is now effective')
		);
	});
	it('shows effective source and does not offer saving after a failed estimate', async () => {
		mocks.preview.mockRejectedValue(new Error('Scope unavailable'));
		await open();
		expect(target.textContent).toContain('90 days');
		target
			.querySelector('form')!
			.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
		await vi.waitFor(() =>
			expect(target.querySelector('[role=alert]')?.textContent).toContain('Scope unavailable')
		);
		expect(button('Save scoped retention').disabled).toBe(true);
	});
});
