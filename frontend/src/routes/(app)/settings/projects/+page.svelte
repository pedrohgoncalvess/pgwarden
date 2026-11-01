<script lang="ts">
	import { profile } from '$lib/access';
	import VisibleProjects from '$lib/components/projects/VisibleProjects.svelte';
	import { onMount } from 'svelte';
	import ProjectForm from '$lib/components/projects/ProjectForm.svelte';
	import ProjectKeys from '$lib/components/projects/ProjectKeys.svelte';
	import {
		createProject,
		listProjects,
		listProjectKeys,
		updateProject,
		rotateProjectKey,
		revokeProjectKey,
		type Project,
		type ProjectKey,
		type ProjectSettings
	} from '$lib/projects-api';
	let projects = $state<Project[]>([]);
	let keys = $state<ProjectKey[]>([]);
	let selected = $state<Project | undefined>();
	let creating = $state(false);
	let busy = $state(false);
	let loading = $state(true);
	let error = $state('');
	let secret = $state('');
	let copied = $state(false);
	let endpoint = $state('/api/v1/ingestion/events');
	const date = (value: string | null) => (value ? new Date(value).toLocaleString() : '—');

	async function loadKeys(id: string) {
		const result = await listProjectKeys(id);
		if (selected?.id === id) keys = result;
	}
	async function load() {
		try {
			projects = await listProjects();
			if (selected) selected = projects.find((project) => project.id === selected?.id);
			if (selected) await loadKeys(selected.id);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not load projects.';
		} finally {
			loading = false;
		}
	}
	async function select(project: Project) {
		selected = project;
		creating = false;
		secret = '';
		keys = [];
		error = '';
		try {
			await loadKeys(project.id);
		} catch (cause) {
			error = String(cause);
		}
	}
	async function refreshActivity() {
		try {
			projects = await listProjects();
			const current = projects.find((project) => project.id === selected?.id);
			if (current && selected) {
				selected.last_event_at = current.last_event_at;
				selected.next_rotation_at = current.next_rotation_at;
				await loadKeys(current.id);
			}
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not refresh activity.';
		}
	}
	async function save(settings: ProjectSettings) {
		busy = true;
		error = '';
		secret = '';
		try {
			if (creating || !selected) {
				const result = await createProject(settings);
				selected = result.project;
				secret = result.credential.key;
				creating = false;
			} else {
				selected = await updateProject(selected.id, settings);
			}
			copied = false;
			await load();
		} finally {
			busy = false;
		}
	}
	async function rotate(hours: number) {
		if (!selected) return;
		busy = true;
		error = '';
		secret = '';
		try {
			secret = (await rotateProjectKey(selected.id, hours)).key;
			copied = false;
			await load();
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Rotation failed.';
		} finally {
			busy = false;
		}
	}
	async function revoke(id: string) {
		if (!selected) return;
		busy = true;
		error = '';
		secret = '';
		try {
			await revokeProjectKey(selected.id, id);
			await load();
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Revocation failed.';
		} finally {
			busy = false;
		}
	}
	async function copyKey() {
		try {
			await navigator.clipboard.writeText(secret);
			copied = true;
		} catch {
			error = 'Clipboard unavailable. Select and copy the key directly.';
		}
	}
	onMount(() => {
		if (!$profile?.is_admin) return;
		endpoint = `${window.location.origin}/api/v1/ingestion/events`;
		void load();
		const timer = window.setInterval(() => {
			if (!busy && !creating) void refreshActivity();
		}, 60_000);
		return () => window.clearInterval(timer);
	});
</script>

{#if !$profile?.is_admin}
<VisibleProjects />
{:else}

<header
	class="fixed top-0 right-0 z-40 flex h-16 app-page-header items-center gap-3 border-b border-outline-variant bg-surface-dim px-container-padding"
>
	<span class="material-symbols-outlined">key</span>
	<h1 class="text-headline-md">Projects & ingestion</h1>
</header>
<main class="space-y-6 px-container-padding pt-24 pb-12 text-on-surface">
	<div class="flex items-start justify-between gap-4">
		<div>
			<h2 class="text-xl font-bold">Connect remote collectors</h2>
			<p class="mt-1 text-sm text-on-surface-variant">
				Each project has independent ingestion credentials. Administrator access required.
			</p>
		</div>
		<button
			class="rounded-lg bg-primary px-4 py-2 text-on-primary disabled:opacity-50"
			disabled={busy}
			onclick={() => {
				creating = true;
				selected = undefined;
				secret = '';
				error = '';
			}}>New project</button
		>
	</div>
	{#if error}<p
			role="alert"
			class="rounded-lg border border-error bg-error-container/20 p-4 text-error"
		>
			{error}
		</p>{/if}
	{#if secret}<section role="status" class="rounded-xl border border-primary bg-primary/10 p-5">
			<h2 class="font-bold">Save this key now</h2>
			<p class="mt-1 text-sm">
				It will not be shown again. Configure it in the sender's Authorization: Bearer header.
			</p>
			<code class="mt-3 block overflow-x-auto select-all rounded bg-surface-container p-3"
				>{secret}</code
			>
			<div class="mt-3 flex gap-4">
				<button class="text-primary" onclick={copyKey}>{copied ? 'Copied' : 'Copy key'}</button
				><button onclick={() => (secret = '')}>Dismiss</button>
			</div>
		</section>{/if}
	<div class="grid gap-6 lg:grid-cols-[260px_1fr]">
		<aside class="space-y-2" aria-label="Projects">
			{#if loading}<p>Loading projects…</p>{:else if projects.length === 0}<p
					class="text-sm text-on-surface-variant"
				>
					Create your first project to receive events.
				</p>{/if}{#each projects as project (project.id)}<button
					class="w-full rounded-xl border p-4 text-left disabled:opacity-50 {selected?.id ===
					project.id
						? 'border-primary bg-primary/10'
						: 'border-outline-variant bg-surface-container'}"
					disabled={busy}
					onclick={() => select(project)}
					><span class="block font-bold">{project.name}</span><span
						class="text-xs text-on-surface-variant"
						>{project.enabled ? 'Receiving enabled' : 'Disabled'}</span
					></button
				>{/each}
		</aside>
		<div class="space-y-6">
			{#if creating || selected}<section
					class="rounded-xl border border-outline-variant bg-surface-container-low p-6"
				>
					<h2 class="mb-4 text-lg font-bold">{creating ? 'New project' : 'Project settings'}</h2>
					<ProjectForm initial={selected} {busy} onsave={save} />
				</section>{/if}
			{#if selected}<section class="space-y-2 rounded-xl border border-outline-variant p-5 text-sm">
					<p><strong>Project ID:</strong> <code class="select-all">{selected.id}</code></p>
					<p><strong>Last received:</strong> {date(selected.last_event_at)}</p>
					<p><strong>Next automatic rotation:</strong> {date(selected.next_rotation_at)}</p>
					<p>
						<strong>POST endpoint:</strong> <code class="break-all select-all">{endpoint}</code>
					</p>
					<p class="text-xs text-on-surface-variant">
						Use HTTPS in production. Keys allow ingestion only. The sender must persist
						replacement_key before acknowledging or deleting its local records.
					</p>
				</section>
				<section class="rounded-xl border border-outline-variant bg-surface-container-low p-5">
					<ProjectKeys {keys} {busy} onrotate={rotate} onrevoke={revoke} />
				</section>{/if}
		</div>
	</div>
</main>

{/if}
