<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { listDatabases } from '$lib/api';

	let error = $state('');

	onMount(async () => {
		try {
			const databases = await listDatabases();
			await goto(databases.length ? `/analytics/${databases[0].id}/deep` : '/servers', {
				replaceState: true
			});
		} catch (err: any) {
			error = err.message || 'Failed to load databases.';
		}
	});
</script>

{#if error}
	<div class="p-4 text-sm text-error">{error}</div>
{/if}
