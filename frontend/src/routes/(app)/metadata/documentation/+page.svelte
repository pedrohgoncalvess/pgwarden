<script lang="ts">
	import { onMount } from 'svelte';
	import {
		attachTagAssignment,
		detachTagAssignment,
		getColumnDocumentation,
		getDatabaseDocumentation,
		getDatabaseSchema,
		getIndexDocumentation,
		getSchemaDocumentation,
		getTableDocumentation,
		listDatabases,
		listServers,
		listTagAssignments,
		listTags,
		putColumnDocumentation,
		putDatabaseDocumentation,
		putIndexDocumentation,
		putSchemaDocumentation,
		putTableDocumentation,
		type DatabaseListItem,
		type DatabaseSchema,
		type SchemaColumn,
		type SchemaIndex,
		type SchemaTable,
		type ServerListItem,
		type TagAssignment,
		type TagAssignmentInput,
		type TagItem
	} from '$lib/api';

	type DocTargetType = 'database' | 'schema' | 'table' | 'column' | 'index';

	type DocTarget = {
		key: string;
		type: DocTargetType;
		label: string;
		subtitle: string;
		id?: string;
		schemaName?: string;
		table?: SchemaTable;
		column?: SchemaColumn;
		index?: SchemaIndex;
	};

	type SchemaGroup = {
		name: string;
		target: DocTarget;
		tables: SchemaTable[];
	};

	const classificationOptions = ['internal', 'public', 'confidential', 'restricted'];

	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let schema = $state<DatabaseSchema | null>(null);
	let tags = $state<TagItem[]>([]);
	let assignments = $state<TagAssignment[]>([]);
	let selectedServerId = $state('');
	let selectedDatabaseId = $state('');
	let selectedTargetKey = $state('');
	let tagToAttachId = $state('');
	let expandedSchemas = $state<string[]>([]);
	let expandedTables = $state<string[]>([]);
	let searchTerm = $state('');
	let description = $state('');
	let owner = $state('');
	let classification = $state('internal');
	let isPii = $state(false);
	let sampleValues = $state('');
	let loading = $state(true);
	let docLoading = $state(false);
	let saving = $state(false);
	let tagSaving = $state(false);
	let error = $state('');

	const selectedDatabase = $derived(
		databases.find((database) => database.id === selectedDatabaseId) ?? null
	);
	const serverDatabases = $derived(
		databases.filter((database) => database.server_id === selectedServerId)
	);
	const databaseTarget = $derived.by(() => buildDatabaseTarget());
	const allTargets = $derived.by(() => buildTargets());
	const selectedTarget = $derived(
		allTargets.find((target) => target.key === selectedTargetKey) ?? databaseTarget
	);
	const schemaGroups = $derived.by(() => buildSchemaGroups());
	const selectedAssignments = $derived.by(() =>
		selectedTarget ? assignments.filter((assignment) => matchesTarget(assignment, selectedTarget)) : []
	);
	const availableTags = $derived(
		tags.filter((tag) => !selectedAssignments.some((assignment) => assignment.tag.id === tag.id))
	);

	$effect(() => {
		if (!tagToAttachId || !availableTags.some((tag) => tag.id === tagToAttachId)) {
			tagToAttachId = availableTags[0]?.id ?? '';
		}
	});

	async function load() {
		try {
			loading = true;
			error = '';
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
			selectedServerId = servers[0]?.id ?? '';
			selectedDatabaseId = firstDatabaseForServer(selectedServerId)?.id ?? '';
			if (selectedServerId) {
				tags = await listTags(selectedServerId);
			}
			await loadDatabaseContext();
		} catch (err: any) {
			handleError(err, 'Failed to load documentation workspace.');
		} finally {
			loading = false;
		}
	}

	async function selectServer() {
		selectedDatabaseId = firstDatabaseForServer(selectedServerId)?.id ?? '';
		selectedTargetKey = '';
		schema = null;
		assignments = [];
		tags = selectedServerId ? await listTags(selectedServerId) : [];
		await loadDatabaseContext();
	}

	async function selectDatabase() {
		selectedTargetKey = '';
		await loadDatabaseContext();
	}

	async function loadDatabaseContext() {
		if (!selectedDatabaseId) {
			resetDoc();
			return;
		}

		try {
			error = '';
			[schema, assignments] = await Promise.all([
				getDatabaseSchema(selectedDatabaseId),
				listTagAssignments(selectedDatabaseId)
			]);
			expandedSchemas = Array.from(new Set(schema.tables.map((table) => table.schema_name))).slice(0, 3);
			expandedTables = [];
			selectedTargetKey = buildDatabaseTarget().key;
			await loadDocumentation(buildDatabaseTarget());
		} catch (err: any) {
			handleError(err, 'Failed to load database documentation context.');
		}
	}

	async function selectTarget(target: DocTarget) {
		selectedTargetKey = target.key;
		await loadDocumentation(target);
	}

	async function loadDocumentation(target: DocTarget) {
		if (!selectedDatabaseId) return;

		try {
			docLoading = true;
			error = '';
			const doc =
				target.type === 'database'
					? await getDatabaseDocumentation(selectedDatabaseId)
					: target.type === 'schema'
						? await getSchemaDocumentation(selectedDatabaseId, target.schemaName ?? '')
						: target.type === 'table'
							? await getTableDocumentation(selectedDatabaseId, target.id ?? '')
							: target.type === 'column'
								? await getColumnDocumentation(selectedDatabaseId, target.id ?? '')
								: await getIndexDocumentation(selectedDatabaseId, target.id ?? '');

			description = doc?.description ?? '';
			owner = 'owner' in (doc ?? {}) ? ((doc as any).owner ?? '') : '';
			classification = 'classification' in (doc ?? {}) ? ((doc as any).classification ?? 'internal') : 'internal';
			isPii = 'is_pii' in (doc ?? {}) ? Boolean((doc as any).is_pii) : false;
			sampleValues = 'sample_values' in (doc ?? {}) ? ((doc as any).sample_values ?? '') : '';
		} catch (err: any) {
			handleError(err, 'Failed to load documentation.');
		} finally {
			docLoading = false;
		}
	}

	async function saveDocumentation() {
		if (!selectedTarget || !selectedDatabaseId) return;

		try {
			saving = true;
			error = '';
			const base = { description: description.trim() || null };

			if (selectedTarget.type === 'database') {
				await putDatabaseDocumentation(selectedDatabaseId, {
					...base,
					owner: owner.trim() || null,
					classification
				});
			} else if (selectedTarget.type === 'schema') {
				await putSchemaDocumentation(selectedDatabaseId, selectedTarget.schemaName ?? '', {
					...base,
					owner: owner.trim() || null,
					classification
				});
			} else if (selectedTarget.type === 'table') {
				await putTableDocumentation(selectedDatabaseId, selectedTarget.id ?? '', {
					...base,
					owner: owner.trim() || null,
					classification
				});
			} else if (selectedTarget.type === 'column') {
				await putColumnDocumentation(selectedDatabaseId, selectedTarget.id ?? '', {
					...base,
					is_pii: isPii,
					sample_values: sampleValues.trim() || null
				});
			} else {
				await putIndexDocumentation(selectedDatabaseId, selectedTarget.id ?? '', base);
			}
		} catch (err: any) {
			handleError(err, 'Failed to save documentation.');
		} finally {
			saving = false;
		}
	}

	async function attachSelectedTag() {
		if (!selectedTarget || !tagToAttachId) return;

		try {
			tagSaving = true;
			error = '';
			await attachTagAssignment(tagToAttachId, assignmentInputForTarget(selectedTarget));
			assignments = await listTagAssignments(selectedDatabaseId);
		} catch (err: any) {
			handleError(err, 'Failed to attach tag.');
		} finally {
			tagSaving = false;
		}
	}

	async function detachSelectedTag(tag: TagItem) {
		if (!selectedTarget) return;

		try {
			tagSaving = true;
			error = '';
			await detachTagAssignment(tag.id, assignmentInputForTarget(selectedTarget));
			assignments = await listTagAssignments(selectedDatabaseId);
		} catch (err: any) {
			handleError(err, 'Failed to detach tag.');
		} finally {
			tagSaving = false;
		}
	}

	function buildDatabaseTarget(): DocTarget {
		return {
			key: `database:${selectedDatabaseId}`,
			type: 'database',
			id: selectedDatabaseId,
			label: selectedDatabase?.name ?? 'Database',
			subtitle: 'Database documentation'
		};
	}

	function firstDatabaseForServer(serverId: string) {
		return databases.find((database) => database.server_id === serverId) ?? null;
	}

	function buildTargets() {
		const targets: DocTarget[] = [buildDatabaseTarget()];
		for (const group of buildSchemaGroups(false)) {
			targets.push(group.target);
			for (const table of group.tables) {
				targets.push(tableTarget(table));
				for (const column of table.columns) targets.push(columnTarget(table, column));
				for (const index of table.indexes) targets.push(indexTarget(table, index));
			}
		}
		return targets;
	}

	function buildSchemaGroups(applySearch = true): SchemaGroup[] {
		const term = searchTerm.trim().toLowerCase();
		const tables = schema?.tables ?? [];
		const grouped = new Map<string, SchemaTable[]>();

		for (const table of tables) {
			const tableMatches =
				!applySearch ||
				!term ||
				table.schema_name.toLowerCase().includes(term) ||
				table.name.toLowerCase().includes(term) ||
				table.columns.some((column) => column.name.toLowerCase().includes(term)) ||
				table.indexes.some((index) => index.name.toLowerCase().includes(term));

			if (!tableMatches) continue;
			grouped.set(table.schema_name, [...(grouped.get(table.schema_name) ?? []), table]);
		}

		return Array.from(grouped.entries())
			.sort(([left], [right]) => left.localeCompare(right))
			.map(([name, tables]) => ({
				name,
				target: schemaTarget(name),
				tables: tables.sort((left, right) => left.name.localeCompare(right.name))
			}));
	}

	function schemaTarget(schemaName: string): DocTarget {
		return {
			key: `schema:${schemaName}`,
			type: 'schema',
			schemaName,
			label: schemaName,
			subtitle: 'Schema documentation'
		};
	}

	function tableTarget(table: SchemaTable): DocTarget {
		return {
			key: `table:${table.id}`,
			type: 'table',
			id: table.id,
			label: table.name,
			subtitle: `${table.schema_name}.${table.name}`,
			table
		};
	}

	function columnTarget(table: SchemaTable, column: SchemaColumn): DocTarget {
		return {
			key: `column:${column.id}`,
			type: 'column',
			id: column.id,
			label: column.name,
			subtitle: `${table.schema_name}.${table.name}.${column.name}`,
			table,
			column
		};
	}

	function indexTarget(table: SchemaTable, index: SchemaIndex): DocTarget {
		return {
			key: `index:${index.id}`,
			type: 'index',
			id: index.id,
			label: index.name,
			subtitle: `${table.schema_name}.${table.name}.${index.name}`,
			table,
			index
		};
	}

	function assignmentInputForTarget(target: DocTarget): TagAssignmentInput {
		if (target.type === 'schema') {
			return {
				scope: 'doc',
				target_type: 'schema',
				database_id: selectedDatabaseId,
				schema_name: target.schemaName
			};
		}

		return {
			scope: 'doc',
			target_type: target.type,
			target_id: target.id,
			database_id: target.type === 'database' ? selectedDatabaseId : null
		};
	}

	function matchesTarget(assignment: TagAssignment, target: DocTarget) {
		if (assignment.scope !== 'doc' || assignment.target_type !== target.type) return false;
		if (target.type === 'schema') {
			return assignment.database_id === selectedDatabaseId && assignment.target_label === target.schemaName;
		}
		return assignment.target_id === target.id;
	}

	function toggleSchema(schemaName: string) {
		expandedSchemas = expandedSchemas.includes(schemaName)
			? expandedSchemas.filter((name) => name !== schemaName)
			: [...expandedSchemas, schemaName];
	}

	function toggleTable(tableId: string) {
		expandedTables = expandedTables.includes(tableId)
			? expandedTables.filter((id) => id !== tableId)
			: [...expandedTables, tableId];
	}

	function resetDoc() {
		description = '';
		owner = '';
		classification = 'internal';
		isPii = false;
		sampleValues = '';
	}

	function targetIcon(type: DocTargetType) {
		return {
			database: 'database',
			schema: 'account_tree',
			table: 'table',
			column: 'view_column',
			index: 'speed'
		}[type];
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
	<span class="material-symbols-outlined text-primary">description</span>
	<h1 class="font-headline-md text-headline-md text-on-background m-0">Metadata</h1>
	<span class="font-label-caps text-[10px] text-on-surface-variant">/ Documentation</span>
</header>

<div class="pt-24 px-container-padding pb-12 space-y-6">
	{#if error}
		<div class="p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3">
			<span class="material-symbols-outlined text-error">error</span>
			<p class="text-sm text-error">{error}</p>
		</div>
	{/if}

	<section class="rounded-lg border border-outline-variant bg-surface-container p-4">
		<div class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(14rem,18rem)_minmax(14rem,18rem)_1fr]">
			<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
				Server
				<select
					bind:value={selectedServerId}
					onchange={selectServer}
					disabled={loading || servers.length <= 1}
					class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-80"
				>
					{#each servers as server}
						<option value={server.id}>{server.name}</option>
					{/each}
				</select>
			</label>
			<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
				Database
				<select
					bind:value={selectedDatabaseId}
					onchange={selectDatabase}
					disabled={loading || serverDatabases.length === 0}
					class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
				>
					{#each serverDatabases as database}
						<option value={database.id}>{database.name}</option>
					{/each}
				</select>
			</label>
			<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
				Search schema, table, column or index
				<div class="flex items-center rounded-lg border border-outline-variant bg-surface-container-high px-3 focus-within:border-primary">
					<span class="material-symbols-outlined mr-2 text-[18px] text-on-surface-variant">search</span>
					<input
						bind:value={searchTerm}
						class="h-10 min-w-0 flex-1 bg-transparent text-sm text-on-surface outline-none"
						placeholder="Search metadata..."
					/>
				</div>
			</label>
		</div>
	</section>

	<div class="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(24rem,34rem)_1fr]">
		<section class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden">
			<div class="border-b border-outline-variant bg-surface-container-low px-4 py-3">
				<h2 class="m-0 font-headline-md text-headline-md">Objects</h2>
			</div>

			<div class="max-h-[calc(100vh-15rem)] overflow-y-auto custom-scrollbar">
				{#if loading}
					<div class="px-4 py-8 text-sm text-on-surface-variant">Loading documentation workspace...</div>
				{:else if !selectedDatabaseId}
					<div class="px-4 py-8 text-sm text-on-surface-variant">No database available for this server.</div>
				{:else}
					<button
						onclick={() => selectTarget(databaseTarget)}
						class="flex w-full items-center gap-3 border-b border-outline-variant/30 px-4 py-3 text-left transition-colors {selectedTarget?.key === databaseTarget.key ? 'bg-secondary-container text-on-secondary-container' : 'hover:bg-surface-container-high text-on-surface'}"
					>
						<span class="material-symbols-outlined text-[20px]">database</span>
						<div class="min-w-0">
							<p class="truncate text-sm font-bold">{databaseTarget.label}</p>
							<p class="truncate text-[11px] opacity-75">Database documentation</p>
						</div>
					</button>

					{#each schemaGroups as group}
						<div class="border-b border-outline-variant/20">
							<div class="flex items-center">
								<button
									onclick={() => toggleSchema(group.name)}
									class="flex h-10 w-10 items-center justify-center text-on-surface-variant hover:text-on-surface"
								>
									<span
										class="material-symbols-outlined text-[18px] transition-transform"
										style="transform: rotate({expandedSchemas.includes(group.name) ? 90 : 0}deg)"
										>chevron_right</span
									>
								</button>
								<button
									onclick={() => selectTarget(group.target)}
									class="flex min-w-0 flex-1 items-center gap-3 px-2 py-3 text-left transition-colors {selectedTarget?.key === group.target.key ? 'bg-secondary-container text-on-secondary-container' : 'hover:bg-surface-container-high text-on-surface'}"
								>
									<span class="material-symbols-outlined text-[20px]">account_tree</span>
									<div class="min-w-0">
										<p class="truncate text-sm font-bold">{group.name}</p>
										<p class="truncate text-[11px] opacity-75">{group.tables.length} tables</p>
									</div>
								</button>
							</div>

							{#if expandedSchemas.includes(group.name)}
								<div class="border-t border-outline-variant/20">
									{#each group.tables as table}
										<div>
											<div class="flex items-center pl-6">
												<button
													onclick={() => toggleTable(table.id)}
													class="flex h-9 w-9 items-center justify-center text-on-surface-variant hover:text-on-surface"
												>
													<span
														class="material-symbols-outlined text-[18px] transition-transform"
														style="transform: rotate({expandedTables.includes(table.id) ? 90 : 0}deg)"
														>chevron_right</span
													>
												</button>
												<button
													onclick={() => selectTarget(tableTarget(table))}
													class="flex min-w-0 flex-1 items-center gap-3 px-2 py-2 text-left transition-colors {selectedTarget?.key === tableTarget(table).key ? 'bg-secondary-container text-on-secondary-container' : 'hover:bg-surface-container-high text-on-surface'}"
												>
													<span class="material-symbols-outlined text-[19px]">table</span>
													<div class="min-w-0">
														<p class="truncate text-sm font-medium">{table.name}</p>
														<p class="truncate text-[11px] opacity-75">
															{table.columns.length} columns / {table.indexes.length} indexes
														</p>
													</div>
												</button>
											</div>

											{#if expandedTables.includes(table.id)}
												<div class="space-y-1 pb-2 pl-16 pr-3">
													{#each table.columns as column}
														<button
															onclick={() => selectTarget(columnTarget(table, column))}
															class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors {selectedTarget?.key === columnTarget(table, column).key ? 'bg-secondary-container text-on-secondary-container' : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'}"
														>
															<span class="material-symbols-outlined text-[16px]">view_column</span>
															<span class="min-w-0 flex-1 truncate">{column.name}</span>
															<span class="truncate text-[10px] opacity-70">{column.data_type}</span>
														</button>
													{/each}
													{#each table.indexes as index}
														<button
															onclick={() => selectTarget(indexTarget(table, index))}
															class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors {selectedTarget?.key === indexTarget(table, index).key ? 'bg-secondary-container text-on-secondary-container' : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'}"
														>
															<span class="material-symbols-outlined text-[16px]">speed</span>
															<span class="min-w-0 flex-1 truncate">{index.name}</span>
															{#if index.is_primary}
																<span class="rounded bg-primary-container px-1.5 py-0.5 text-[10px] text-on-primary-container">PK</span>
															{:else if index.is_unique}
																<span class="rounded bg-tertiary-container px-1.5 py-0.5 text-[10px] text-on-tertiary-container">Unique</span>
															{/if}
														</button>
													{/each}
												</div>
											{/if}
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/each}
				{/if}
			</div>
		</section>

		<section class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden">
			<div class="border-b border-outline-variant bg-surface-container-low px-5 py-4">
				<div class="flex items-start gap-3">
					<span class="material-symbols-outlined mt-0.5 text-primary">{targetIcon(selectedTarget.type)}</span>
					<div class="min-w-0 flex-1">
						<h2 class="m-0 truncate font-headline-md text-headline-md">{selectedTarget.label}</h2>
						<p class="mt-1 truncate text-xs text-on-surface-variant">{selectedTarget.subtitle}</p>
					</div>
				</div>
			</div>

			<div class="space-y-6 p-5">
				<section>
					<div class="mb-3 flex items-center justify-between gap-3">
						<h3 class="m-0 text-sm font-bold text-on-surface">Tags</h3>
						{#if tags.length === 0}
							<a href="/metadata/tags" class="text-xs font-bold text-primary hover:underline">Create tags</a>
						{/if}
					</div>

					<div class="flex flex-wrap gap-2">
						{#if selectedAssignments.length === 0}
							<span class="text-sm text-on-surface-variant">No tags assigned.</span>
						{:else}
							{#each selectedAssignments as assignment}
								<button
									onclick={() => detachSelectedTag(assignment.tag)}
									disabled={tagSaving}
									class="inline-flex items-center gap-1 rounded-full border border-outline-variant bg-surface-container-high px-3 py-1 text-xs font-bold text-on-surface hover:border-error hover:text-error disabled:opacity-60"
								>
									<span class="h-2.5 w-2.5 rounded-full" style={`background: ${assignment.tag.color ?? '#6366F1'}`}></span>
									{assignment.tag.name}
									<span class="material-symbols-outlined text-[14px]">close</span>
								</button>
							{/each}
						{/if}
					</div>

					<div class="mt-3 flex flex-wrap gap-2">
						<select
							bind:value={tagToAttachId}
							disabled={tagSaving || availableTags.length === 0}
							class="min-w-52 rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-60"
						>
							{#each availableTags as tag}
								<option value={tag.id}>{tag.name}</option>
							{/each}
						</select>
						<button
							onclick={attachSelectedTag}
							disabled={tagSaving || !tagToAttachId}
							class="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary disabled:opacity-50"
						>
							<span class="material-symbols-outlined text-[18px]">label</span>
							Add tag
						</button>
					</div>
				</section>

				<section class="space-y-4">
					<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
						{#if selectedTarget.type === 'database' || selectedTarget.type === 'schema' || selectedTarget.type === 'table'}
							<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
								Owner
								<input
									bind:value={owner}
									disabled={docLoading}
									class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-60"
									placeholder="Team, person, area..."
								/>
							</label>
							<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
								Classification
								<select
									bind:value={classification}
									disabled={docLoading}
									class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-60"
								>
									{#each classificationOptions as option}
										<option value={option}>{option}</option>
									{/each}
								</select>
							</label>
						{/if}

						{#if selectedTarget.type === 'column'}
							<label class="flex items-center gap-3 rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface">
								<input type="checkbox" bind:checked={isPii} disabled={docLoading} />
								Contains PII
							</label>
							<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
								Sample values
								<input
									bind:value={sampleValues}
									disabled={docLoading}
									class="rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-60"
									placeholder="Example format, no sensitive values"
								/>
							</label>
						{/if}
					</div>

					<label class="flex flex-col gap-2 text-xs text-on-surface-variant">
						Documentation
						<textarea
							bind:value={description}
							disabled={docLoading}
							rows="12"
							class="resize-y rounded-lg border border-outline-variant bg-surface-container-high px-3 py-3 text-sm leading-6 text-on-surface outline-none focus:border-primary disabled:opacity-60"
							placeholder="Describe purpose, ownership rules, data meaning, lifecycle notes, caveats, or operational context."
						></textarea>
					</label>

					<div class="flex items-center gap-3">
						<button
							onclick={saveDocumentation}
							disabled={saving || docLoading || !selectedDatabaseId}
							class="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary disabled:opacity-50"
						>
							<span class="material-symbols-outlined text-[18px]">save</span>
							Save documentation
						</button>
						{#if docLoading}
							<span class="text-xs text-on-surface-variant">Loading documentation...</span>
						{/if}
					</div>
				</section>
			</div>
		</section>
	</div>
</div>
