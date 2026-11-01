<script lang="ts">
	import { onMount, tick, untrack } from 'svelte';
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import { nextOption, findOption, type SelectOption } from '$lib/selectNavigation';

	type Props = Omit<
		HTMLButtonAttributes,
		'children' | 'value' | 'onchange' | 'onclick' | 'type'
	> & {
		options: SelectOption[];
		value?: string;
		placeholder?: string;
		name?: string;
		onchange?: (value: string) => void;
	};
	let {
		options,
		value = $bindable(''),
		placeholder = 'Select an option',
		disabled = false,
		class: className = '',
		id,
		name,
		onchange,
		...attributes
	}: Props = $props();
	const uid = $props.id();
	let trigger = $state<HTMLButtonElement>();
	let panel = $state<HTMLDivElement>();
	let open = $state(false);
	let activeIndex = $state(-1);
	let typed = '';
	let lastTypedAt = 0;
	const selectedIndex = $derived(options.findIndex((option) => option.value === value));
	const selected = $derived(options[selectedIndex]);
	const listId = `${uid}-options`;

	function positionPanel() {
		if (!open || !trigger || !panel) return;
		const rect = trigger.getBoundingClientRect();
		const width = Math.min(Math.max(rect.width, 200), window.innerWidth - 16);
		const below = window.innerHeight - rect.bottom - 12;
		const above = rect.top - 12;
		const upwards = below < 180 && above > below;
		const height = Math.max(40, Math.min(280, upwards ? above : below));
		panel.style.width = `${width}px`;
		panel.style.maxHeight = `${height}px`;
		panel.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`;
		panel.style.top = `${upwards ? Math.max(8, rect.top - Math.min(panel.scrollHeight, height) - 6) : rect.bottom + 6}px`;
	}

	function close(returnFocus = false) {
		open = false;
		panel?.hidePopover?.();
		typed = '';
		if (returnFocus) trigger?.focus();
	}

	async function show() {
		if (disabled || open) return;
		activeIndex = options.findIndex((option) => option.value === value && !option.disabled);
		if (activeIndex < 0) activeIndex = nextOption(options, -1, 1);
		open = true;
		await tick();
		if (!open || !panel) return;
		panel.showPopover?.();
		positionPanel();
		scrollToActive();
	}

	function scrollToActive() {
		panel
			?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`)
			?.scrollIntoView({ block: 'nearest' });
	}

	function choose(index: number) {
		const option = options[index];
		if (disabled || !option || option.disabled) return;
		const changed = value !== option.value;
		value = option.value;
		close(true);
		if (changed) onchange?.(option.value);
	}

	async function handleKey(event: KeyboardEvent) {
		if (disabled) return;
		if (event.key === 'Tab') {
			close();
			return;
		}
		if (event.key === 'Escape' && open) {
			event.preventDefault();
			event.stopPropagation();
			close(true);
			return;
		}
		if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
			event.preventDefault();
			const wasOpen = open;
			await show();
			if (event.key === 'Home') activeIndex = nextOption(options, -1, 1);
			else if (event.key === 'End') activeIndex = nextOption(options, 0, -1);
			else if (wasOpen)
				activeIndex = nextOption(options, activeIndex, event.key === 'ArrowDown' ? 1 : -1);
			await tick();
			scrollToActive();
			return;
		}
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			if (open) choose(activeIndex);
			else await show();
			return;
		}
		if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
			event.preventDefault();
			const now = Date.now();
			typed = now - lastTypedAt > 650 ? event.key : typed + event.key;
			lastTypedAt = now;
			await show();
			let found = findOption(options, typed, typed.length > 1 ? activeIndex - 1 : activeIndex);
			if (found < 0 && [...typed].every((char) => char === typed[0]))
				found = findOption(options, event.key, activeIndex);
			if (found >= 0) activeIndex = found;
			await tick();
			scrollToActive();
		}
	}

	onMount(() => {
		const outside = (event: PointerEvent) => {
			if (!open) return;
			const target = event.target as Node;
			if (!trigger?.contains(target) && !panel?.contains(target)) close();
		};
		const reposition = () => positionPanel();
		window.addEventListener('pointerdown', outside);
		window.addEventListener('resize', reposition);
		window.addEventListener('scroll', reposition, true);
		return () => {
			window.removeEventListener('pointerdown', outside);
			window.removeEventListener('resize', reposition);
			window.removeEventListener('scroll', reposition, true);
		};
	});

	$effect(() => {
		const items = options;
		if (disabled && open) close();
		if (open)
			untrack(() => {
				if (!items[activeIndex] || items[activeIndex].disabled)
					activeIndex = nextOption(items, -1, 1);
				void tick().then(positionPanel);
			});
	});
</script>

<span class="app-select {className}">
	{#if name}<input type="hidden" {name} {value} {disabled} />{/if}
	<button
		{...attributes}
		id={id ?? `${uid}-trigger`}
		bind:this={trigger}
		type="button"
		class="select-trigger"
		{disabled}
		role="combobox"
		aria-haspopup="listbox"
		aria-expanded={open}
		aria-controls={listId}
		aria-activedescendant={open && activeIndex >= 0 ? `${uid}-option-${activeIndex}` : undefined}
		onclick={() => (open ? close() : show())}
		onkeydown={handleKey}
	>
		<span class="select-value" class:placeholder={!selected}>{selected?.label ?? placeholder}</span>
		<svg
			class="select-chevron"
			class:expanded={open}
			width="16"
			height="16"
			viewBox="0 0 24 24"
			fill="none"
			aria-hidden="true"
			><path
				d="m6 9 6 6 6-6"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
			/></svg
		>
	</button>
	<div
		bind:this={panel}
		id={listId}
		class="select-menu"
		class:is-open={open}
		popover="manual"
		role="listbox"
		tabindex="-1"
		aria-label={attributes['aria-label'] ?? 'Options'}
	>
		{#if open}{#each options as option, index (index)}
				<button
					type="button"
					role="option"
					id={`${uid}-option-${index}`}
					data-index={index}
					tabindex="-1"
					class="select-option"
					class:highlighted={index === activeIndex}
					aria-selected={index === selectedIndex}
					disabled={option.disabled}
					onpointermove={() => {
						if (!option.disabled) activeIndex = index;
					}}
					onclick={() => choose(index)}
					onkeydown={handleKey}
				>
					<span>{option.label}</span>
					{#if index === selectedIndex}<svg
							width="16"
							height="16"
							viewBox="0 0 24 24"
							fill="none"
							aria-hidden="true"
							><path
								d="m5 12 4 4L19 6"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
							/></svg
						>{/if}
				</button>
			{:else}<p class="select-empty">No options available</p>{/each}{/if}
	</div>
</span>

<style>
	.app-select {
		display: inline-flex;
		min-width: 0;
		max-width: 100%;
		vertical-align: middle;
		font-size: var(--select-font-size, 13px);
	}
	.select-trigger {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		width: 100%;
		min-width: 0;
		min-height: var(--select-min-height, 36px);
		padding: var(--select-padding, 7px 10px);
		border: 1px solid var(--select-border, var(--color-outline-variant));
		border-radius: 5px;
		background: var(--select-background, var(--color-surface-container-low));
		color: var(--color-on-surface);
		font: inherit;
		text-align: left;
		transition:
			border-color 120ms,
			background-color 120ms;
	}
	.select-trigger:hover:not(:disabled) {
		background: var(--color-surface-container);
		border-color: var(--color-outline);
	}
	.select-trigger:focus-visible,
	.select-trigger[aria-expanded='true'] {
		border-color: var(--color-primary);
		outline: 2px solid color-mix(in srgb, var(--color-primary) 20%, transparent);
		outline-offset: 1px;
	}
	.select-value {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.placeholder {
		color: var(--color-on-surface-variant);
	}
	.select-chevron {
		flex-shrink: 0;
		color: var(--color-on-surface-variant);
		transition: transform 120ms;
	}
	.select-chevron.expanded {
		transform: rotate(180deg);
	}
	.select-menu {
		display: none;
		position: fixed;
		inset: auto;
		margin: 0;
		padding: 4px;
		overflow-y: auto;
		overscroll-behavior: contain;
		scrollbar-width: thin;
		box-sizing: border-box;
		border: 1px solid var(--color-outline-variant);
		border-radius: 6px;
		background: var(--color-surface-container-high);
		color: var(--color-on-surface);
		box-shadow: 0 8px 24px #0005;
		z-index: 200;
	}
	.select-menu.is-open {
		display: block;
		animation: select-in 120ms ease-out;
	}
	.select-option {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		width: 100%;
		min-height: 36px;
		padding: 8px 10px;
		border-radius: 3px;
		color: var(--color-on-surface);
		font: 13px/20px var(--font-sans);
		text-align: left;
		overflow-wrap: anywhere;
	}
	.select-option span {
		flex: 1;
	}
	.select-option svg {
		flex-shrink: 0;
	}
	.select-option.highlighted {
		background: var(--color-surface-container-highest);
	}
	.select-option[aria-selected='true'] {
		color: var(--color-primary);
	}
	.select-option:disabled {
		opacity: 0.45;
	}
	.select-empty {
		padding: 12px;
		color: var(--color-on-surface-variant);
		font-size: 13px;
	}
	@keyframes select-in {
		from {
			opacity: 0;
			transform: translateY(-3px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
</style>
