import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, unmount, tick } from 'svelte';
import Configuration from '../routes/(app)/alerts/configuration/+page.svelte';

const mocks = vi.hoisted(() => ({ list: vi.fn(), patch: vi.fn() }));
vi.mock('$lib/api', () => ({
	listNotifierChannels: mocks.list,
	patchNotifierChannel: mocks.patch
}));
vi.mock('$lib/access', async () => {
	const { writable } = await import('svelte/store');
	return { profile: writable(null), can: () => true };
});

describe('write-only alert credentials', () => {
	let component: ReturnType<typeof mount>;
	let target: HTMLDivElement;
	beforeEach(() => {
		vi.resetAllMocks();
		target = document.createElement('div');
		document.body.append(target);
		mocks.list.mockResolvedValue([{ id: 1, name: 'email', enabled: false, has_credentials: true }]);
		mocks.patch.mockResolvedValue({});
	});
	afterEach(async () => {
		if (component) await unmount(component);
		target.remove();
	});
	async function open() {
		component = mount(Configuration, { target });
		await vi.waitFor(() => expect(target.querySelector('#channel-1-password')).not.toBeNull());
	}
	async function fill(key: string, value: string) {
		const input = target.querySelector<HTMLInputElement>(`#channel-1-${key}`)!;
		input.value = value;
		input.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
	}
	const save = () => target.querySelector('button')!.click();
	it('opens saved credentials as empty fields', async () => {
		await open();
		for (const input of target.querySelectorAll<HTMLInputElement>('input:not([type=checkbox])')) {
			expect(input.value).toBe('');
		}
	});
	it('rejects a password-only SMTP replacement', async () => {
		await open();
		await fill('password', 'new-secret');
		save();
		await vi.waitFor(() => expect(target.textContent).toContain('Replace the complete SMTP'));
		expect(mocks.patch).not.toHaveBeenCalled();
	});
	it('sends all SMTP fields and clears the draft even if reload fails', async () => {
		await open();
		mocks.list.mockRejectedValueOnce(new Error('Reload failed'));
		await fill('host', 'smtp.example.com');
		await fill('port', '587');
		await fill('from', 'sender@example.com');
		await fill('to', 'recipient@example.com');
		save();
		await vi.waitFor(() =>
			expect(mocks.patch).toHaveBeenCalledWith(1, {
				credentials: {
					host: 'smtp.example.com',
					port: 587,
					username: '',
					password: '',
					from: 'sender@example.com',
					to: 'recipient@example.com'
				}
			})
		);
		await vi.waitFor(() => expect(target.textContent).toContain('Reload failed'));
		expect(target.querySelector<HTMLInputElement>('#channel-1-host')!.value).toBe('');
	});
	it('changes activation without sending saved credentials', async () => {
		await open();
		const input = target.querySelector<HTMLInputElement>('input[type=checkbox]')!;
		input.checked = true;
		input.dispatchEvent(new Event('change', { bubbles: true }));
		await tick();
		save();
		await vi.waitFor(() => expect(mocks.patch).toHaveBeenCalledWith(1, { enabled: true }));
	});
});
