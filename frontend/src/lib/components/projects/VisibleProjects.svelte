<script lang="ts">
	import { onMount } from 'svelte';
	import { apiFetch, authHeaders } from '$lib/auth';
	import { listServers, listDatabases, type ServerListItem, type DatabaseListItem } from '$lib/api';
	let projects = $state<{ id: string; name: string }[]>([]);
	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let loading = $state(true);
	let error = $state('');
	onMount(async () => {
		try {
			const response = await apiFetch('/api/v1/catalog/projects', { headers: authHeaders() });
			if (!response.ok) throw new Error('Could not load projects.');
			projects = await response.json();
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
		} catch (cause) {
			error = String(cause);
		} finally {
			loading = false;
		}
	});
</script>

<div class="mx-auto max-w-5xl space-y-5 text-on-surface">
	<h1 class="text-2xl font-bold">Projects</h1>
	<p class="text-sm text-on-surface-variant">Projects and resources available through your role.</p>
	{#if error}<p role="alert" class="text-error">{error}</p>{/if}
	{#if loading}<p>Loading projects…</p>{:else}
		{#each projects as project (project.id)}
			<section class="rounded-xl border border-outline-variant bg-surface-container-low p-5">
				<h2 class="mb-3 text-lg font-bold">{project.name}</h2>
				{#each servers.filter((s) => s.project_id === project.id) as server (server.id)}
					<div class="mb-3 rounded-lg border border-outline-variant p-4">
						<h3 class="font-semibold">{server.name}</h3>
						<ul class="mt-2 space-y-1 text-sm text-on-surface-variant">
							{#each databases.filter((d) => d.server_id === server.id) as database (database.id)}
								<li>{database.name}</li>
							{:else}<li>No databases available.</li>{/each}
						</ul>
					</div>
				{:else}<p class="text-sm text-on-surface-variant">
						No servers available in this project.
					</p>{/each}
			</section>
		{:else}<p>No projects are assigned to your role.</p>{/each}
	{/if}
</div>
