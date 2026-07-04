<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { listDatabases } from '$lib/api';

	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		try {
			const databases = await listDatabases();
			if (databases[0]) {
				await goto(`/metadata/${databases[0].id}/documentation`, { replaceState: true });
			}
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || 'Failed to load databases.';
		} finally {
			loading = false;
		}
	});
</script>

<div class="pt-24 px-container-padding pb-12">
	<div class="rounded-lg border border-outline-variant bg-surface-container px-6 py-16 text-center">
		<span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3">description</span>
		<p class="font-bold text-on-surface mb-1">Documentation</p>
		<p class="text-sm text-on-surface-variant">
			{#if loading}
				Opening database documentation context...
			{:else if error}
				{error}
			{:else}
				No databases registered.
			{/if}
		</p>
	</div>
</div>
