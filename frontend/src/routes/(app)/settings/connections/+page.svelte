<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { listServers } from '$lib/api';
	import type { ServerListItem } from '$lib/api';

	let servers = $state<ServerListItem[]>([]);
	let loading = $state(true);
	let error = $state('');
	let showSelector = $state(false);

	async function load() {
		try {
			loading = true;
			error = '';
			servers = await listServers();

			if (servers.length === 0) {
				return;
			}

			if (servers.length === 1) {
				await goto(`/settings/connections/${servers[0].id}`, { replaceState: true });
				return;
			}

			showSelector = true;
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || 'Failed to load servers.';
		} finally {
			loading = false;
		}
	}

	function selectServer(server: ServerListItem) {
		goto(`/settings/connections/${server.id}`, { replaceState: true });
	}

	onMount(() => load());
</script>


<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex items-center px-container-padding h-16 gap-3"
>
	<span class="material-symbols-outlined text-on-surface-variant">settings</span>
	<h1 class="font-headline-md text-headline-md text-on-background m-0">Settings</h1>
</header>


<div class="pt-24 px-container-padding pb-12">
	{#if loading}
		<div class="flex items-center justify-center py-24">
			<svg
				class="h-8 w-8 animate-spin text-primary"
				xmlns="http://www.w3.org/2000/svg"
				fill="none"
				viewBox="0 0 24 24"
			>
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"
				></circle>
				<path
					class="opacity-75"
					fill="currentColor"
					d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
				></path>
			</svg>
		</div>
	{:else if error}
		<div
			class="p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3"
		>
			<span class="material-symbols-outlined text-error">error</span>
			<p class="text-sm text-error">{error}</p>
		</div>
	{:else if servers.length === 0}
		<div class="settings-card px-6 py-12 flex flex-col items-center text-center">
			<span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3">dns</span>
			<p class="text-on-surface font-bold mb-1">No servers registered</p>
			<p class="text-sm text-on-surface-variant">
				Add a server from the main dashboard to get started.
			</p>
		</div>
	{/if}
</div>

{#if showSelector}
	<div class="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4">
		<div class="settings-card w-full max-w-md p-6 shadow-floating">
			<div class="flex items-center gap-3 mb-2">
				<div
					class="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center flex-shrink-0"
				>
					<span class="material-symbols-outlined text-primary text-[20px]">dns</span>
				</div>
				<div>
					<h2 class="font-headline-md text-headline-md font-bold text-on-surface m-0">
						Select a server
					</h2>
					<p class="text-[12px] text-on-surface-variant mt-0.5">
						Choose which server you want to manage connections for.
					</p>
				</div>
			</div>

			<div class="space-y-2 mt-5">
				{#each servers as server}
					<button
						onclick={() => selectServer(server)}
						class="w-full flex items-center gap-3 px-4 py-3 rounded-lg border border-outline-variant bg-surface-container text-left transition-colors hover:bg-surface-variant cursor-pointer"
					>
						<span class="material-symbols-outlined text-on-surface-variant">dns</span>
						<div class="min-w-0">
							<p class="font-bold text-on-surface text-sm truncate">{server.name}</p>
							<p class="text-[11px] text-on-surface-variant">{server.status}</p>
						</div>
						<span class="material-symbols-outlined text-on-surface-variant ml-auto"
							>chevron_right</span
						>
					</button>
				{/each}
			</div>
		</div>
	</div>
{/if}

<style>
	.settings-card {
		background: rgba(26, 33, 31, 0.95);
		border: 1px solid rgba(133, 148, 144, 0.15);
		border-radius: 14px;
	}
	.modal-overlay {
		background: rgba(0, 0, 0, 0.65);
		backdrop-filter: blur(5px);
	}
</style>
