// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, unmount, tick } from 'svelte';
import Select from './Select.svelte';
import SelectFixture from './__tests__/SelectFixture.svelte';

const options = [
	{ value: '', label: 'Choose a database', disabled: true },
	{ value: 'main', label: 'Main' },
	{ value: 'offline', label: 'Offline', disabled: true },
	{ value: 'reports', label: 'Reports' }
];

describe('Select interaction', () => {
	let component: ReturnType<typeof mount>;
	let target: HTMLDivElement;
	beforeEach(() => {
		target = document.createElement('div');
		document.body.append(target);
		HTMLElement.prototype.scrollIntoView = vi.fn();
		HTMLElement.prototype.showPopover = vi.fn();
		HTMLElement.prototype.hidePopover = vi.fn();
	});
	afterEach(async () => {
		if (component) await unmount(component);
		target.remove();
		vi.restoreAllMocks();
	});

	async function setup(disabled = false) {
		const onchange = vi.fn();
		component = mount(Select, {
			target,
			props: { options, value: 'main', 'aria-label': 'Database', disabled, onchange }
		});
		await tick();
		return { trigger: target.querySelector<HTMLButtonElement>('[role="combobox"]')!, onchange };
	}
	async function key(trigger: HTMLElement, key: string) {
		trigger.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
		await tick();
		await tick();
	}

	it('skips disabled options, selects with Enter and returns focus to the trigger', async () => {
		const { trigger, onchange } = await setup();
		trigger.focus();
		await key(trigger, 'ArrowDown');
		expect(trigger.getAttribute('aria-expanded')).toBe('true');
		await key(trigger, 'ArrowDown');
		await key(trigger, 'Enter');
		expect(onchange).toHaveBeenCalledWith('reports');
		expect(trigger.textContent).toContain('Reports');
		expect(trigger.getAttribute('aria-expanded')).toBe('false');
		expect(document.activeElement).toBe(trigger);
	});

	it('cancels with Escape and closes on Tab without changing the value', async () => {
		const { trigger, onchange } = await setup();
		await key(trigger, 'Enter');
		await key(trigger, 'End');
		await key(trigger, 'Escape');
		expect(onchange).not.toHaveBeenCalled();
		expect(trigger.textContent).toContain('Main');
		await key(trigger, 'Enter');
		await key(trigger, 'Tab');
		expect(trigger.getAttribute('aria-expanded')).toBe('false');
	});

	it('supports typing to find an option and mouse selection', async () => {
		const { trigger, onchange } = await setup();
		await key(trigger, 'r');
		await vi.waitFor(() =>
			expect(
				document.getElementById(trigger.getAttribute('aria-activedescendant')!)?.textContent
			).toContain('Reports')
		);
		target.querySelector<HTMLButtonElement>('[role="option"][data-index="3"]')!.click();
		await tick();
		expect(onchange).toHaveBeenCalledWith('reports');
	});

	it('does not open when disabled', async () => {
		const { trigger, onchange } = await setup(true);
		trigger.click();
		await tick();
		expect(trigger.disabled).toBe(true);
		expect(trigger.getAttribute('aria-expanded')).toBe('false');
		expect(onchange).not.toHaveBeenCalled();
	});

	it('updates parent bindings before calling the change handler', async () => {
		const onchange = vi.fn();
		component = mount(SelectFixture, { target, props: { options, onchange } });
		await tick();
		const trigger = target.querySelector<HTMLButtonElement>('[role="combobox"]')!;
		await key(trigger, 'Enter');
		await key(trigger, 'End');
		await key(trigger, 'Enter');
		expect(onchange).toHaveBeenCalledWith('reports');
		expect(target.querySelector('output')?.textContent).toBe('reports');
		expect(
			new FormData(
				Object.assign(document.createElement('form'), { innerHTML: target.innerHTML })
			).get('database')
		).toBe('reports');
	});

	it('closes when clicking outside without moving focus back to the select', async () => {
		const { trigger, onchange } = await setup();
		await key(trigger, 'Enter');
		const outside = document.createElement('input');
		document.body.append(outside);
		outside.focus();
		outside.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }));
		await tick();
		expect(trigger.getAttribute('aria-expanded')).toBe('false');
		expect(document.activeElement).toBe(outside);
		expect(onchange).not.toHaveBeenCalled();
		outside.remove();
	});
});
