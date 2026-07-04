<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		attachTagAssignment,
		createTag,
		deleteTag,
		detachTagAssignment,
		getDatabaseSchema,
		getQueryAnalytics,
		listDatabases,
		listServers,
		listTagAssignments,
		listTags,
		updateTag,
		type DatabaseListItem,
		type DatabaseSchema,
		type QueryAnalyticsResponse,
		type ServerListItem,
		type TagAssignment,
		type TagAssignmentInput,
		type TagAssignmentScope,
		type TagAssignmentTargetType,
		type TagItem
	} from '$lib/api';

	type TargetOption = TagAssignmentInput & { key: string; label: string };
	type TargetTypeOption = { scope: TagAssignmentScope; value: TagAssignmentTargetType; label: string };

	const colors = ['#6366F1', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6', '#06B6D4'];
	const targetTypes: TargetTypeOption[] = [
		{ scope: 'object', value: 'database', label: 'Database object' },
		{ scope: 'object', value: 'table', label: 'Table object' },
		{ scope: 'object', value: 'column', label: 'Column object' },
		{ scope: 'object', value: 'index', label: 'Index object' },
		{ scope: 'object', value: 'native_query', label: 'Query object' },
		{ scope: 'doc', value: 'database', label: 'Database documentation' },
		{ scope: 'doc', value: 'schema', label: 'Schema documentation' },
		{ scope: 'doc', value: 'table', label: 'Table documentation' },
		{ scope: 'doc', value: 'column', label: 'Column documentation' },
		{ scope: 'doc', value: 'index', label: 'Index documentation' }
	];

	let tags = $state<TagItem[]>([]);
	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let schema = $state<DatabaseSchema | null>(null);
	let queryAnalytics = $state<QueryAnalyticsResponse | null>(null);
	let assignments = $state<TagAssignment[]>([]);
	let selectedServerId = $state($page.params.server_id ?? '');
	let selectedDatabaseId = $state('');
	let selectedTagId = $state('');
	let selectedTargetTypeKey = $state('object:database');
	let selectedTargetKey = $state('');
	let editingTagId = $state<string | null>(null);
	let formName = $state('');
	let formDescription = $state('');
	let formColor = $state(colors[0]);
	let formType = $state('default');
	let loading = $state(true);
	let saving = $state(false);
	let error = $state('');

	const serverDatabases = $derived(databases.filter((database) => database.server_id === selectedServerId));
	const selectedDatabase = $derived(serverDatabases.find((database) => database.id === selectedDatabaseId) ?? null);
	const selectedTag = $derived(tags.find((tag) => tag.id === selectedTagId) ?? null);
	const selectedTargetType = $derived(
		targetTypes.find((type) => `${type.scope}:${type.value}` === selectedTargetTypeKey) ?? targetTypes[0]
	);
	const targets = $derived.by(() => buildTargets());
	const selectedTarget = $derived(targets.find((target) => target.key === selectedTargetKey) ?? null);

	$effect(() => {
		if (!targets.some((target) => target.key === selectedTargetKey)) {
			selectedTargetKey = targets[0]?.key ?? '';
		}
	});

	async function load() {
		try {
			loading = true;
			error = '';
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
			if (!servers.some((server) => server.id === selectedServerId)) {
				if (servers[0]) {
					selectedServerId = servers[0].id;
					await goto(`/metadata/tags/${servers[0].id}`, { replaceState: true });
				} else {
					tags = [];
					selectedTagId = '';
					selectedDatabaseId = '';
					assignments = [];
					return;
				}
			}
			tags = await listTags(selectedServerId);
			selectedTagId = tags[0]?.id ?? '';
			selectedDatabaseId = serverDatabases[0]?.id ?? '';
			if (selectedDatabaseId) {
				await loadDatabaseContext();
			}
		} catch (err: any) {
			handleError(err, 'Failed to load tags.');
		} finally {
			loading = false;
		}
	}

	async function selectServer() {
		if (selectedServerId) {
			await goto(`/metadata/tags/${selectedServerId}`);
			tags = await listTags(selectedServerId);
			selectedTagId = tags[0]?.id ?? '';
			selectedDatabaseId = serverDatabases[0]?.id ?? '';
			await loadDatabaseContext();
		}
	}

	async function loadDatabaseContext() {
		if (!selectedDatabaseId) {
			schema = null;
			queryAnalytics = null;
			assignments = [];
			return;
		}

		try {
			error = '';
			[schema, queryAnalytics, assignments] = await Promise.all([
				getDatabaseSchema(selectedDatabaseId),
				getQueryAnalytics(selectedDatabaseId, { preset: '1w', limit: 100 }),
				listTagAssignments(selectedDatabaseId)
			]);
		} catch (err: any) {
			handleError(err, 'Failed to load database tag context.');
		}
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
		formName = tag.name;
		formDescription = tag.description ?? '';
		formColor = tag.color ?? colors[0];
		formType = tag.type;
	}

	async function saveTag() {
		if (!formName.trim()) return;
		try {
			saving = true;
			error = '';
			const payload = {
				server_id: selectedServerId,
				name: formName.trim(),
				description: formDescription.trim() || null,
				color: formColor,
				type: formType.trim() || 'default'
			};
			if (editingTagId) {
				const { server_id: _serverId, ...updatePayload } = payload;
				const updated = await updateTag(editingTagId, updatePayload);
				tags = tags.map((tag) => (tag.id === updated.id ? updated : tag));
			} else {
				const created = await createTag(payload);
				tags = [created, ...tags];
				selectedTagId = created.id;
			}
			startCreate();
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
			assignments = assignments.filter((item) => item.tag.id !== tag.id);
			if (selectedTagId === tag.id) selectedTagId = tags[0]?.id ?? '';
		} catch (err: any) {
			handleError(err, 'Failed to delete tag.');
		}
	}

	async function attachSelectedTag() {
		if (!selectedTag || !selectedTarget) return;
		try {
			saving = true;
			error = '';
			await attachTagAssignment(selectedTag.id, selectedTarget);
			assignments = await listTagAssignments(selectedDatabaseId);
		} catch (err: any) {
			handleError(err, 'Failed to attach tag.');
		} finally {
			saving = false;
		}
	}

	async function detachAssignment(assignment: TagAssignment) {
		try {
			error = '';
			await detachTagAssignment(assignment.tag.id, assignmentToInput(assignment));
			assignments = assignments.filter(
				(item) =>
					!(
						item.tag.id === assignment.tag.id &&
						item.scope === assignment.scope &&
						item.target_type === assignment.target_type &&
						item.target_id === assignment.target_id &&
						item.database_id === assignment.database_id &&
						item.query_hash === assignment.query_hash &&
						item.target_label === assignment.target_label
					)
			);
		} catch (err: any) {
			handleError(err, 'Failed to detach tag.');
		}
	}

	function buildTargets(): TargetOption[] {
		if (!selectedDatabase) return [];
		const scope = selectedTargetType.scope;
		const targetType = selectedTargetType.value;

		if (targetType === 'database') {
			return [
				withKey({
					scope,
					target_type: 'database',
					target_id: selectedDatabase.id,
					database_id: selectedDatabase.id,
					label: selectedDatabase.name
				})
			];
		}

		if (targetType === 'schema') {
			const names = Array.from(new Set(schema?.tables.map((table) => table.schema_name) ?? []));
			return names.map((name) =>
				withKey({
					scope,
					target_type: 'schema',
					database_id: selectedDatabase.id,
					schema_name: name,
					label: name
				})
			);
		}

		if (targetType === 'table') {
			return (schema?.tables ?? []).map((table) =>
				withKey({
					scope,
					target_type: 'table',
					target_id: table.id,
					label: `${table.schema_name}.${table.name}`
				})
			);
		}

		if (targetType === 'column') {
			return (schema?.tables ?? []).flatMap((table) =>
				table.columns.map((column) =>
					withKey({
						scope,
						target_type: 'column',
						target_id: column.id,
						label: `${table.schema_name}.${table.name}.${column.name}`
					})
				)
			);
		}

		if (targetType === 'index') {
			return (schema?.tables ?? []).flatMap((table) =>
				table.indexes.map((index) =>
					withKey({
						scope,
						target_type: 'index',
						target_id: index.id,
						label: `${table.schema_name}.${table.name}.${index.name}`
					})
				)
			);
		}

		if (targetType === 'native_query') {
			return (queryAnalytics?.items ?? [])
				.filter((query) => query.query_hash)
				.map((query) =>
					withKey({
						scope: 'object',
						target_type: 'native_query',
						database_id: selectedDatabase.id,
						query_hash: query.query_hash,
						label: query.query_preview
					})
				);
		}

		return [];
	}

	function withKey<T extends TagAssignmentInput & { label: string }>(target: T): T & { key: string } {
		return { ...target, key: JSON.stringify(target) };
	}

	function assignmentToInput(assignment: TagAssignment): TagAssignmentInput {
		return {
			scope: assignment.scope,
			target_type: assignment.target_type,
			target_id: assignment.target_id,
			database_id: assignment.database_id,
			schema_name: assignment.target_type === 'schema' ? assignment.target_label : null,
			query_hash: assignment.query_hash
		};
	}

	function assignmentTypeLabel(assignment: TagAssignment) {
		return (
			targetTypes.find(
				(type) => type.scope === assignment.scope && type.value === assignment.target_type
			)?.label ?? assignment.target_type
		);
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
		<div class="p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3">
			<span class="material-symbols-outlined text-error">error</span>
			<p class="text-sm text-error">{error}</p>
		</div>
	{/if}

	<section class="rounded-lg border border-outline-variant bg-surface-container p-4">
		<div class="flex flex-wrap items-end gap-4">
			<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
				Server context
				<select
					bind:value={selectedServerId}
					onchange={selectServer}
					disabled={loading || servers.length <= 1}
					class="min-w-56 rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-80"
				>
					{#each servers as server}
						<option value={server.id}>{server.name}</option>
					{/each}
				</select>
			</label>
			<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
				Database target context
				<select
					bind:value={selectedDatabaseId}
					onchange={loadDatabaseContext}
					disabled={loading || serverDatabases.length === 0}
					class="min-w-56 rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
				>
					{#each serverDatabases as database}
						<option value={database.id}>{database.name}</option>
					{/each}
				</select>
			</label>
		</div>
	</section>

	<div class="grid grid-cols-1 xl:grid-cols-[minmax(18rem,22rem)_1fr] gap-6">
		<section class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden">
			<div class="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3">
				<h2 class="m-0 font-headline-md text-headline-md">Tags</h2>
				<button
					onclick={startCreate}
					class="flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-on-primary"
				>
					<span class="material-symbols-outlined text-[14px]">add</span>
					New
				</button>
			</div>
			<div class="divide-y divide-outline-variant/20">
				{#if loading}
					<div class="px-4 py-8 text-sm text-on-surface-variant">Loading tags...</div>
				{:else if tags.length === 0}
					<div class="px-4 py-8 text-sm text-on-surface-variant">No tags created yet.</div>
				{:else}
					{#each tags as tag}
						<div class="flex items-center gap-3 px-4 py-3">
							<button
								onclick={() => (selectedTagId = tag.id)}
								class="min-w-0 flex-1 text-left cursor-pointer"
							>
								<div class="flex items-center gap-2">
									<span class="h-3 w-3 rounded-full" style={`background: ${tag.color ?? colors[0]}`}></span>
									<p class="truncate text-sm font-bold text-on-surface">{tag.name}</p>
								</div>
								<p class="mt-0.5 truncate text-[11px] text-on-surface-variant">{tag.type}</p>
							</button>
							<button onclick={() => startEdit(tag)} class="text-on-surface-variant hover:text-primary">
								<span class="material-symbols-outlined text-[18px]">edit</span>
							</button>
							<button onclick={() => removeTag(tag)} class="text-on-surface-variant hover:text-error">
								<span class="material-symbols-outlined text-[18px]">delete</span>
							</button>
						</div>
					{/each}
				{/if}
			</div>
		</section>

		<div class="space-y-6">
			<section class="rounded-lg border border-outline-variant bg-surface-container p-5">
				<h2 class="m-0 mb-4 font-headline-md text-headline-md">
					{editingTagId ? 'Edit tag' : 'Create tag'}
				</h2>
				<div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
					<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
						Name
						<input
							bind:value={formName}
							class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
						/>
					</label>
					<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
						Type
						<input
							bind:value={formType}
							class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
						/>
					</label>
					<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
						Color
						<div class="flex items-center gap-2">
							<input type="color" bind:value={formColor} class="h-10 w-12 rounded border border-outline-variant bg-surface-container-high" />
							<input
								bind:value={formColor}
								class="min-w-0 flex-1 rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
							/>
						</div>
					</label>
					<label class="flex flex-col gap-2 text-xs text-on-surface-variant lg:col-span-3">
						Description
						<textarea
							bind:value={formDescription}
							rows="4"
							placeholder="Describe when this tag should be used, ownership notes, remediation context, or any internal convention."
							class="resize-y rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
						></textarea>
					</label>
				</div>
				<div class="mt-4 flex gap-3">
					<button
						onclick={saveTag}
						disabled={saving || !formName.trim()}
						class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary disabled:opacity-50"
					>
						<span class="material-symbols-outlined text-[18px]">save</span>
						Save tag
					</button>
					<button onclick={startCreate} class="rounded-lg border border-outline-variant px-4 py-2 text-sm font-bold text-on-surface">
						Clear
					</button>
				</div>
			</section>

			<section class="rounded-lg border border-outline-variant bg-surface-container p-5">
				<h2 class="m-0 mb-4 font-headline-md text-headline-md">Assign tag</h2>
				<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
					<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
						Tag
						<select bind:value={selectedTagId} class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary">
							{#each tags as tag}
								<option value={tag.id}>{tag.name}</option>
							{/each}
						</select>
					</label>
					<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
						Target type
						<select bind:value={selectedTargetTypeKey} class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary">
							{#each targetTypes as type}
								<option value={`${type.scope}:${type.value}`}>{type.label}</option>
							{/each}
						</select>
					</label>
					<label class="flex flex-col gap-2 text-xs text-on-surface-variant xl:col-span-2">
						Target
						<select bind:value={selectedTargetKey} class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary">
							{#each targets as target}
								<option value={target.key}>{target.label}</option>
							{/each}
						</select>
					</label>
				</div>
				<button
					onclick={attachSelectedTag}
					disabled={saving || !selectedTag || !selectedTarget}
					class="mt-4 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary disabled:opacity-50"
				>
					<span class="material-symbols-outlined text-[18px]">link</span>
					Attach tag
				</button>
			</section>

			<section class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden">
				<div class="border-b border-outline-variant bg-surface-container-low px-4 py-3">
					<h2 class="m-0 font-headline-md text-headline-md">Assignments</h2>
				</div>
				<div class="divide-y divide-outline-variant/20">
					{#if assignments.length === 0}
						<div class="px-4 py-8 text-sm text-on-surface-variant">No assignments for this database.</div>
					{:else}
						{#each assignments as assignment}
							<div class="flex items-center gap-3 px-4 py-3">
								<span class="h-3 w-3 rounded-full" style={`background: ${assignment.tag.color ?? colors[0]}`}></span>
								<div class="min-w-0 flex-1">
									<p class="truncate text-sm font-bold text-on-surface">{assignment.tag.name}</p>
									<p class="truncate text-[11px] text-on-surface-variant">
										{assignmentTypeLabel(assignment)} / {assignment.target_label}
									</p>
								</div>
								<button onclick={() => detachAssignment(assignment)} class="text-on-surface-variant hover:text-error">
									<span class="material-symbols-outlined text-[18px]">link_off</span>
								</button>
							</div>
						{/each}
					{/if}
				</div>
			</section>
		</div>
	</div>
</div>
