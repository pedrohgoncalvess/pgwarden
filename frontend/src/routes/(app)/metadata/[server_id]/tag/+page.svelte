<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { selectedServerId } from '$lib/stores/selectedServer';
	import {
		createTag,
		deleteTag,
		listServers,
		listTags,
		updateTag,
		type ServerListItem,
		type TagItem
	} from '$lib/api';

	const colors = ['#6366F1', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6', '#06B6D4'];

	let tags = $state<TagItem[]>([]);
	let servers = $state<ServerListItem[]>([]);
	let selectedServerIdLocal = $state($page.params.server_id ?? '');
	let selectedTagId = $state('');
	let editingTagId = $state<string | null>(null);
	let formName = $state('');
	let formDescription = $state('');
	let formColor = $state(colors[0]);
	let formType = $state('default');
	let searchTerm = $state('');
	let loading = $state(true);
	let saving = $state(false);
	let error = $state('');

	const selectedServer = $derived(
		servers.find((server) => server.id === selectedServerIdLocal) ?? null
	);
	const selectedTag = $derived(tags.find((tag) => tag.id === selectedTagId) ?? null);
	const isEditing = $derived(Boolean(editingTagId));
	const serverIsFixed = $derived(servers.length <= 1);
	const tagTypes = $derived.by(() => Array.from(new Set(tags.map((tag) => tag.type))).sort());
	const filteredTags = $derived.by(() => {
		const term = searchTerm.trim().toLowerCase();
		if (!term) return tags;

		return tags.filter((tag) =>
			[tag.name, tag.type, tag.description ?? ''].some((value) =>
				value.toLowerCase().includes(term)
			)
		);
	});

	async function load() {
		try {
			loading = true;
			error = '';
			servers = await listServers();

			if (!servers.some((server) => server.id === selectedServerIdLocal)) {
				if (!servers[0]) {
					tags = [];
					selectedTagId = '';
					return;
				}

				selectedServerIdLocal = servers[0].id;
				await goto(`/metadata/${selectedServerIdLocal}/tag`, { replaceState: true });
			}

			selectedServerId.set(selectedServerIdLocal);
			await loadTagsForServer();
		} catch (err: any) {
			handleError(err, 'Failed to load tags.');
		} finally {
			loading = false;
		}
	}

	async function selectServer() {
		if (!selectedServerIdLocal) return;

		try {
			loading = true;
			error = '';
			await goto(`/metadata/${selectedServerIdLocal}/tag`);
			selectedServerId.set(selectedServerIdLocal);
			await loadTagsForServer();
			startCreate();
		} catch (err: any) {
			handleError(err, 'Failed to load tags.');
		} finally {
			loading = false;
		}
	}

	async function loadTagsForServer() {
		tags = await listTags(selectedServerIdLocal);
		selectedTagId = tags[0]?.id ?? '';
	}

	function startCreate() {
		editingTagId = null;
		formName = '';
		formDescription = '';
		formColor = colors[0];
		formType = 'default';
	}

	function startEdit(tag: TagItem) {
		editingTagId = tag.id;
		selectedTagId = tag.id;
		formName = tag.name;
		formDescription = tag.description ?? '';
		formColor = tag.color ?? colors[0];
		formType = tag.type || 'default';
	}

	async function saveTag() {
		if (!formName.trim() || !selectedServerIdLocal) return;

		try {
			saving = true;
			error = '';
			const payload = {
				server_id: selectedServerIdLocal,
				name: formName.trim(),
				description: formDescription.trim() || null,
				color: formColor,
				type: formType.trim() || 'default'
			};

			if (editingTagId) {
				const { server_id: _serverId, ...updatePayload } = payload;
				const updated = await updateTag(editingTagId, updatePayload);
				tags = tags.map((tag) => (tag.id === updated.id ? updated : tag));
				selectedTagId = updated.id;
				startEdit(updated);
			} else {
				const created = await createTag(payload);
				tags = [created, ...tags];
				selectedTagId = created.id;
				startCreate();
			}
		} catch (err: any) {
			handleError(err, 'Failed to save tag.');
		} finally {
			saving = false;
		}
	}

	async function removeTag(tag: TagItem) {
		if (!window.confirm(`Delete tag "${tag.name}"?`)) return;

		try {
			error = '';
			await deleteTag(tag.id);
			tags = tags.filter((item) => item.id !== tag.id);
			if (selectedTagId === tag.id) selectedTagId = tags[0]?.id ?? '';
			if (editingTagId === tag.id) startCreate();
		} catch (err: any) {
			handleError(err, 'Failed to delete tag.');
		}
	}

	function handleError(err: any, fallback: string) {
		if (err.message?.includes('401')) {
			localStorage.removeItem('token');
			window.location.href = '/login';
			return;
		}
		error = err.message || fallback;
	}

	onMount(() => load());
</script>

<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex items-center px-container-padding h-16 gap-3"
>
	<span class="material-symbols-outlined text-primary">label</span>
	<h1 class="font-headline-md text-headline-md text-on-background m-0">Metadata</h1>
	<span class="font-label-caps text-[10px] text-on-surface-variant">/ Tags</span>
</header>

<div class="pt-24 px-container-padding pb-12 space-y-6">
	{#if error}
		<div
			class="p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3"
		>
			<span class="material-symbols-outlined text-error">error</span>
			<p class="text-sm text-error">{error}</p>
		</div>
	{/if}

	<section class="rounded-lg border border-outline-variant bg-surface-container p-4">
		<div class="flex flex-wrap items-center justify-between gap-4">
			<div class="min-w-0">
				<p class="m-0 text-xs font-bold uppercase tracking-wide text-on-surface-variant">
					Server tag catalog
				</p>
				<h2 class="m-0 mt-1 truncate font-headline-md text-headline-md text-on-surface">
					{selectedServer?.name ?? 'Select a server'}
				</h2>
			</div>

			<div class="flex flex-wrap items-end gap-4">
				<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
					Server
					<select
						bind:value={selectedServerIdLocal}
						onchange={selectServer}
						disabled={loading || serverIsFixed}
						class="min-w-56 rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-80"
					>
						{#each servers as server}
							<option value={server.id}>{server.name}</option>
						{/each}
					</select>
				</label>

				<div class="rounded-lg border border-outline-variant bg-surface-container-high px-4 py-2">
					<p class="m-0 text-[11px] uppercase tracking-wide text-on-surface-variant">Tags</p>
					<p class="m-0 text-lg font-bold text-on-surface">{tags.length}</p>
				</div>
			</div>
		</div>
	</section>

	<div class="grid grid-cols-1 xl:grid-cols-[minmax(20rem,26rem)_1fr] gap-6">
		<section class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden">
			<div
				class="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3"
			>
				<h2 class="m-0 font-headline-md text-headline-md">Tags</h2>
				<button
					type="button"
					onclick={startCreate}
					class="flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-on-primary"
				>
					<span class="material-symbols-outlined text-[14px]">add</span>
					New
				</button>
			</div>

			<div class="border-b border-outline-variant px-4 py-3">
				<label class="relative block">
					<span
						class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-on-surface-variant"
					>
						search
					</span>
					<input
						bind:value={searchTerm}
						placeholder="Search tags"
						class="w-full rounded-lg border border-outline-variant bg-surface-container-high py-2 pl-10 pr-3 text-sm text-on-surface outline-none focus:border-primary"
					/>
				</label>
			</div>

			<div
				class="max-h-[calc(100vh-24rem)] min-h-80 overflow-y-auto divide-y divide-outline-variant/20"
			>
				{#if loading}
					<div class="px-4 py-8 text-sm text-on-surface-variant">Loading tags...</div>
				{:else if tags.length === 0}
					<div class="px-4 py-8 text-sm text-on-surface-variant">No tags created yet.</div>
				{:else if filteredTags.length === 0}
					<div class="px-4 py-8 text-sm text-on-surface-variant">No tags match this search.</div>
				{:else}
					{#each filteredTags as tag}
						<div
							class={`flex items-center gap-3 px-4 py-3 transition-colors ${
								selectedTagId === tag.id
									? 'bg-primary-container/20'
									: 'hover:bg-surface-container-high'
							}`}
						>
							<button
								type="button"
								onclick={() => (selectedTagId = tag.id)}
								class="min-w-0 flex-1 text-left"
							>
								<div class="flex items-center gap-2">
									<span
										class="h-3 w-3 shrink-0 rounded-full"
										style={`background-color: ${tag.color ?? colors[0]}`}
									></span>
									<p class="truncate text-sm font-bold text-on-surface">{tag.name}</p>
								</div>
								<p class="mt-1 truncate text-[11px] text-on-surface-variant">
									{tag.description || tag.type}
								</p>
							</button>
							<button
								type="button"
								onclick={() => startEdit(tag)}
								class="text-on-surface-variant hover:text-primary"
								title="Edit tag"
							>
								<span class="material-symbols-outlined text-[18px]">edit</span>
							</button>
							<button
								type="button"
								onclick={() => removeTag(tag)}
								class="text-on-surface-variant hover:text-error"
								title="Delete tag"
							>
								<span class="material-symbols-outlined text-[18px]">delete</span>
							</button>
						</div>
					{/each}
				{/if}
			</div>
		</section>

		<div class="space-y-6">
			<section class="rounded-lg border border-outline-variant bg-surface-container p-5">
				<div class="mb-5 flex flex-wrap items-start justify-between gap-4">
					<div>
						<p class="m-0 text-xs font-bold uppercase tracking-wide text-on-surface-variant">
							{isEditing ? 'Editing' : 'New tag'}
						</p>
						<h2 class="m-0 mt-1 font-headline-md text-headline-md">
							{isEditing ? 'Edit tag' : 'Create tag'}
						</h2>
					</div>

					<div
						class="flex items-center gap-2 rounded-full border border-outline-variant bg-surface-container-high px-3 py-1.5"
					>
						<span class="h-3 w-3 rounded-full" style={`background-color: ${formColor || colors[0]}`}
						></span>
						<span class="max-w-52 truncate text-xs font-bold text-on-surface">
							{formName || 'Tag preview'}
						</span>
					</div>
				</div>

				<div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
					<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
						Name
						<input
							bind:value={formName}
							placeholder="production, pii, critical"
							class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
						/>
					</label>

					<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
						Category
						<input
							bind:value={formType}
							list="tag-types"
							placeholder="default"
							class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
						/>
						<datalist id="tag-types">
							{#each tagTypes as type}
								<option value={type}></option>
							{/each}
						</datalist>
					</label>

					<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
						Color
						<div class="flex items-center gap-2">
							<input
								type="color"
								bind:value={formColor}
								class="h-10 w-12 rounded border border-outline-variant bg-surface-container-high"
							/>
							<input
								bind:value={formColor}
								class="min-w-0 flex-1 rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
							/>
						</div>
					</label>

					<div class="lg:col-span-3 flex flex-wrap gap-2">
						{#each colors as color}
							<button
								type="button"
								onclick={() => (formColor = color)}
								class={`h-8 w-8 rounded-full border ${
									formColor === color
										? 'border-on-surface ring-2 ring-primary'
										: 'border-outline-variant'
								}`}
								style={`background-color: ${color}`}
								title={color}
							></button>
						{/each}
					</div>

					<label class="flex flex-col gap-2 text-xs text-on-surface-variant lg:col-span-3">
						Description
						<textarea
							bind:value={formDescription}
							rows="5"
							placeholder="Add context for when this tag should be used, ownership notes, remediation details, or internal conventions."
							class="resize-y rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
						></textarea>
					</label>
				</div>

				<div class="mt-5 flex flex-wrap items-center gap-3">
					<button
						type="button"
						onclick={saveTag}
						disabled={saving || !formName.trim()}
						class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary disabled:opacity-50"
					>
						<span class="material-symbols-outlined text-[18px]">save</span>
						{saving ? 'Saving...' : isEditing ? 'Save changes' : 'Create tag'}
					</button>

					{#if isEditing}
						<button
							type="button"
							onclick={startCreate}
							class="rounded-lg border border-outline-variant px-4 py-2 text-sm font-bold text-on-surface hover:bg-surface-container-high"
						>
							Cancel edit
						</button>
					{:else}
						<button
							type="button"
							onclick={startCreate}
							class="rounded-lg border border-outline-variant px-4 py-2 text-sm font-bold text-on-surface hover:bg-surface-container-high"
						>
							Clear
						</button>
					{/if}
				</div>
			</section>

			<section class="rounded-lg border border-outline-variant bg-surface-container p-5">
				<div class="flex items-start gap-3">
					<span class="material-symbols-outlined text-primary">sell</span>
					<div class="min-w-0">
						<h2 class="m-0 font-headline-md text-headline-md">Selected tag</h2>
						{#if selectedTag}
							<div class="mt-3 flex flex-wrap items-center gap-2">
								<span
									class="h-3 w-3 rounded-full"
									style={`background-color: ${selectedTag.color ?? colors[0]}`}
								></span>
								<p class="m-0 text-sm font-bold text-on-surface">{selectedTag.name}</p>
								<span
									class="rounded-full bg-surface-container-high px-2 py-1 text-[11px] text-on-surface-variant"
								>
									{selectedTag.type}
								</span>
							</div>
							<p class="mt-3 text-sm leading-6 text-on-surface-variant">
								{selectedTag.description || 'No description provided.'}
							</p>
						{:else}
							<p class="mt-3 text-sm text-on-surface-variant">
								Select a tag from the catalog or create a new one.
							</p>
						{/if}
					</div>
				</div>
			</section>
		</div>
	</div>
</div>
