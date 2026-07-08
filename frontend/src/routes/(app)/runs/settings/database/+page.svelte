<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { listDatabases } from '$lib/api';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';

	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		try {
			const databases = await listDatabases();
			const database =
				databases.find((db) => db.id === $selectedDatabaseId) ?? databases[0] ?? null;
			if (database) {
				await goto(`/runs/${database.id}/settings/database`, { replaceState: true });
			} else {
				loading = false;
			}
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || 'Failed to load databases.';
			loading = false;
		}
	});
</script>

<div class="pt-24 px-container-padding pb-12">
	<div class="settings-card px-6 py-16 flex flex-col items-center text-center">
		<span class="material-symbols-outlined text-[48px] text-on-surface-variant mb-4">database</span>
		<p class="font-bold text-on-surface text-lg mb-2">Database-level collector settings</p>
		<p class="text-sm text-on-surface-variant max-w-xs">
			{#if loading}
				Opening database collector settings...
			{:else if error}
				{error}
			{:else}
				No databases registered.
			{/if}
		</p>
	</div>
</div>

<style>
	.settings-card {
		background: rgba(26, 33, 31, 0.95);
		border: 1px solid rgba(133, 148, 144, 0.15);
		border-radius: 14px;
	}
</style>
