<script lang="ts">
	import { optionalDays, type Project, type ProjectSettings } from '$lib/projects-api';
	let {
		initial,
		busy = false,
		onsave
	}: {
		initial?: Project;
		busy?: boolean;
		onsave: (settings: ProjectSettings) => Promise<void>;
	} = $props();
	let name = $state('');
	let enabled = $state(true);
	let expiration = $state('');
	let rotation = $state('');
	let grace = $state(24);
	let error = $state('');
	$effect(() => {
		name = initial?.name ?? '';
		enabled = initial?.enabled ?? true;
		expiration = initial?.key_expiration_days?.toString() ?? '';
		rotation = initial?.rotation_interval_days?.toString() ?? '';
		grace = initial?.rotation_grace_hours ?? 24;
		error = '';
	});
	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		try {
			const lifetime = optionalDays(expiration);
			const interval = optionalDays(rotation);
			if (interval !== null && grace <= 0)
				throw new Error('Automatic rotation requires an overlap period.');
			if (interval !== null && lifetime !== null && interval >= lifetime)
				throw new Error('Rotate before the key expires.');
			await onsave({
				name: name.trim(),
				enabled,
				key_expiration_days: lifetime,
				rotation_interval_days: interval,
				rotation_grace_hours: grace
			});
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not save project.';
		}
	}
</script>

<form onsubmit={submit} class="space-y-4">
	<label class="block text-sm"
		>Project name
		<input class="field mt-1" bind:value={name} required maxlength="100" disabled={busy} />
	</label>
	<div class="grid gap-4 sm:grid-cols-2">
		<label class="block text-sm"
			>Key lifetime (days, optional)
			<input
				class="field mt-1"
				type="text"
				inputmode="numeric"
				placeholder="No expiration"
				bind:value={expiration}
				disabled={busy}
			/>
		</label>
		<label class="block text-sm"
			>Automatic rotation (days, optional)
			<input
				class="field mt-1"
				type="text"
				inputmode="numeric"
				placeholder="Manual only"
				bind:value={rotation}
				disabled={busy}
			/>
		</label>
	</div>
	<label class="block text-sm"
		>Automatic rotation overlap (hours)
		<input
			class="field mt-1"
			type="number"
			min="0"
			max="168"
			step="1"
			bind:value={grace}
			required
			disabled={busy}
		/>
	</label>
	<p class="text-xs text-on-surface-variant">
		During overlap, the sender receives the replacement key in ingestion responses. Lifetime changes
		apply to newly issued keys.
	</p>
	<label class="flex items-center gap-2 text-sm"
		><input type="checkbox" role="switch" bind:checked={enabled} disabled={busy} /> Accept events for this project</label
	>
	{#if error}<p role="alert" class="text-sm text-error">{error}</p>{/if}
	<button
		class="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary disabled:opacity-50"
		disabled={busy || !name.trim()}
		>{busy ? 'Saving…' : initial ? 'Save settings' : 'Create project and key'}</button
	>
</form>

<style>
	.field {
		width: 100%;
		border: 1px solid var(--color-outline-variant);
		border-radius: 8px;
		padding: 0.65rem;
		background: var(--color-surface-container);
		color: var(--color-on-surface);
	}
</style>
