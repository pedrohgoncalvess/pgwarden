<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { getDatabaseSchema, getDatabaseSchemaHistory, listDatabases } from '$lib/api';
	import type {
		DatabaseListItem,
		DatabaseSchema,
		SchemaColumn,
		SchemaHistoryItem,
		SchemaTable
	} from '$lib/api';

	type Position = {
		x: number;
		y: number;
	};

	type DragState = {
		tableId: string;
		offsetX: number;
		offsetY: number;
		pointerId: number;
		startX: number;
		startY: number;
	};

	type ForeignKeyLink = {
		id: string;
		fromTable: SchemaTable;
		fromColumn: SchemaColumn;
		toTable: SchemaTable;
		toColumn: SchemaColumn | null;
	};

	const tableWidth = 380;
	const rowHeight = 36;
	const headerHeight = 62;
	const tableGapX = 130;
	const tableGapY = 110;
	const baseCanvasWidth = 2200;
	const minZoom = 0.45;
	const maxZoom = 1.6;

	let databases = $state<DatabaseListItem[]>([]);
	let selectedDb = $state<DatabaseListItem | null>(null);
	let schema = $state<DatabaseSchema | null>(null);
	let loading = $state(true);
	let schemaLoading = $state(false);
	let error = $state('');
	let positions = $state<Record<string, Position>>({});
	let dragState = $state<DragState | null>(null);
	let zoom = $state(1);
	let searchTerm = $state('');
	let selectedSchema = $state('');
	let schemaScrollEl = $state<HTMLDivElement | null>(null);
	let boardViewportWidth = $state(0);
	let userMovedLayout = $state(false);
	let dragMoved = $state(false);
	let selectedTableId = $state<string | null>(null);
	let sidebarOpen = $state(false);
	let historyItems = $state<SchemaHistoryItem[]>([]);
	let historyLoading = $state(false);
	let historyError = $state('');
	let tooltip = $state<{ text: string; x: number; y: number } | null>(null);
	let tooltipTimeout: ReturnType<typeof setTimeout> | null = null;
	let schemaHelpOpen = $state(false);
	let panState = $state<{
		pointerId: number;
		startX: number;
		startY: number;
		startScrollLeft: number;
		startScrollTop: number;
	} | null>(null);
	let isPanning = $state(false);

	const tables = $derived(schema?.tables ?? []);
	const schemaNames = $derived([...new Set(tables.map((table) => table.schema_name))].sort());
	const visibleTables = $derived(filterTables(tables, searchTerm, selectedSchema));
	const tableById = $derived(new Map(tables.map((table) => [table.id, table])));
	const selectedTable = $derived(selectedTableId ? (tableById.get(selectedTableId) ?? null) : null);
	const columnById = $derived(
		new Map(tables.flatMap((table) => table.columns.map((column) => [column.id, column])))
	);
	const foreignKeyLinks = $derived(buildForeignKeyLinks(visibleTables));
	const canvasSize = $derived(getCanvasSize(visibleTables, positions));
	const scaledCanvasWidth = $derived(canvasSize.width * zoom);
	const boardWidth = $derived(Math.max(scaledCanvasWidth, boardViewportWidth));
	const worldOffsetX = $derived(Math.max(0, (boardViewportWidth - scaledCanvasWidth) / 2));

	async function loadDatabases() {
		try {
			loading = true;
			error = '';
			databases = await listDatabases();

			if (databases.length === 0) {
				return;
			}

			const routeDbId = $page.params.database_id;
			const database = databases.find((db) => db.id === routeDbId) ?? databases[0];
			if (database.id !== routeDbId) {
				await goto(`/schema/${database.id}`, { replaceState: true });
				return;
			}
			await selectDatabase(database);
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
	}

	async function selectDatabase(database: DatabaseListItem) {
		selectedDb = database;
		selectedDatabaseId.set(database.id);
		schemaLoading = true;
		error = '';

		try {
			const nextSchema = await getDatabaseSchema(database.id);
			schema = {
				...nextSchema,
				tables: nextSchema.tables
					.map((table) => ({
						...table,
						columns: [...table.columns].sort((a, b) => a.ordinal_position - b.ordinal_position),
						indexes: [...table.indexes].sort((a, b) => Number(b.is_primary) - Number(a.is_primary))
					}))
					.sort((a, b) => `${a.schema_name}.${a.name}`.localeCompare(`${b.schema_name}.${b.name}`))
			};
			selectedSchema = '';
			searchTerm = '';
			zoom = 1;
			userMovedLayout = false;
			closeSidebar();
			positions = createInitialPositions(schema.tables, selectedSchema);
			await centerBoard();
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			schema = null;
			positions = {};
			error = err.message || 'Failed to load schema.';
		} finally {
			schemaLoading = false;
		}
	}

	function filterTables(
		schemaTables: SchemaTable[],
		term: string,
		schemaName: string
	): SchemaTable[] {
		const normalizedTerm = term.trim().toLowerCase();

		return schemaTables.filter((table) => {
			const matchesSchema = !schemaName || table.schema_name === schemaName;
			const qualifiedName = `${table.schema_name}.${table.name}`.toLowerCase();
			const matchesSearch =
				!normalizedTerm ||
				qualifiedName.includes(normalizedTerm) ||
				table.schema_name.toLowerCase().includes(normalizedTerm) ||
				table.name.toLowerCase().includes(normalizedTerm);

			return matchesSchema && matchesSearch;
		});
	}

	function createInitialPositions(
		schemaTables: SchemaTable[],
		prioritySchema = ''
	): Record<string, Position> {
		const grouped = new Map<string, SchemaTable[]>();
		for (const table of schemaTables) {
			grouped.set(table.schema_name, [...(grouped.get(table.schema_name) ?? []), table]);
		}

		const nextPositions: Record<string, Position> = {};
		let yOffset = 56;
		const orderedGroups = [...grouped.entries()].sort(([schemaA], [schemaB]) => {
			if (schemaA === prioritySchema) return -1;
			if (schemaB === prioritySchema) return 1;
			return schemaA.localeCompare(schemaB);
		});

		for (const [schemaName, group] of orderedGroups) {
			const columnsPerRow = getColumnsPerRow(group.length);
			for (let rowStart = 0; rowStart < group.length; rowStart += columnsPerRow) {
				const rowTables = group.slice(rowStart, rowStart + columnsPerRow);
				const rowColumns = rowTables.length;
				const rowWidth = rowColumns * tableWidth + Math.max(0, rowColumns - 1) * tableGapX;
				const startX = Math.max(40, Math.round((baseCanvasWidth - rowWidth) / 2));
				const rowIndex = rowStart / columnsPerRow;
				const rowShift = rowIndex % 2 === 0 ? -54 : 54;

				rowTables.forEach((table, col) => {
					const xJitter = deterministicOffset(`${schemaName}:${table.name}:x`, 42);
					const yJitter = deterministicOffset(`${schemaName}:${table.name}:y`, 28);
					const centerBias = rowColumns < columnsPerRow ? 0 : rowShift;

					nextPositions[table.id] = {
						x: Math.max(40, startX + col * (tableWidth + tableGapX) + centerBias + xJitter),
						y: yOffset + yJitter
					};
				});

				yOffset += Math.max(...rowTables.map(getTableHeight)) + tableGapY;
			}

			yOffset += schemaName === prioritySchema ? 36 : 72;
		}

		return nextPositions;
	}

	function getColumnsPerRow(tableCount: number): number {
		const maxColumns = Math.floor((baseCanvasWidth - 80 + tableGapX) / (tableWidth + tableGapX));
		if (tableCount <= 1) return 1;
		if (tableCount <= 4) return Math.min(2, maxColumns);
		if (tableCount <= 10) return Math.min(3, maxColumns);
		return Math.max(3, Math.min(4, maxColumns));
	}

	function deterministicOffset(seed: string, radius: number): number {
		let hash = 0;
		for (let index = 0; index < seed.length; index += 1) {
			hash = (hash * 31 + seed.charCodeAt(index)) >>> 0;
		}
		return (hash % (radius * 2 + 1)) - radius;
	}

	function buildForeignKeyLinks(schemaTables: SchemaTable[]): ForeignKeyLink[] {
		const localTableById = new Map(schemaTables.map((table) => [table.id, table]));
		const localColumnById = new Map(
			schemaTables.flatMap((table) => table.columns.map((column) => [column.id, column]))
		);

		return schemaTables.flatMap((fromTable) =>
			fromTable.columns
				.filter((column) => column.fk_table_id)
				.map((fromColumn) => {
					const toTable = localTableById.get(fromColumn.fk_table_id ?? '');
					if (!toTable) return null;

					return {
						id: `${fromTable.id}:${fromColumn.id}`,
						fromTable,
						fromColumn,
						toTable,
						toColumn: fromColumn.fk_column_id
							? (localColumnById.get(fromColumn.fk_column_id) ?? null)
							: null
					};
				})
				.filter((link): link is ForeignKeyLink => link !== null)
		);
	}

	function getTableHeight(table: SchemaTable): number {
		const indexHeight = table.indexes.length > 0 ? 42 : 0;
		return headerHeight + table.columns.length * rowHeight + indexHeight + 12;
	}

	function getCanvasSize(schemaTables: SchemaTable[], tablePositions: Record<string, Position>) {
		let width = baseCanvasWidth;
		let height = 720;

		for (const table of schemaTables) {
			const position = tablePositions[table.id];
			if (!position) continue;
			width = Math.max(width, position.x + tableWidth + 96);
			height = Math.max(height, position.y + getTableHeight(table) + 96);
		}

		return { width, height };
	}

	function getColumnIndex(table: SchemaTable, columnId: string | null): number {
		if (!columnId) return 0;
		const index = table.columns.findIndex((column) => column.id === columnId);
		return Math.max(index, 0);
	}

	function anchorFor(table: SchemaTable, columnId: string | null, side: 'left' | 'right') {
		const position = positions[table.id] ?? { x: 0, y: 0 };
		return {
			x: side === 'left' ? position.x : position.x + tableWidth,
			y: position.y + headerHeight + getColumnIndex(table, columnId) * rowHeight + rowHeight / 2
		};
	}

	function linkPath(link: ForeignKeyLink): string {
		const from = anchorFor(link.fromTable, link.fromColumn.id, 'right');
		const to = anchorFor(link.toTable, link.toColumn?.id ?? null, 'left');
		const distance = Math.max(80, Math.abs(to.x - from.x) / 2);
		return `M ${from.x} ${from.y} C ${from.x + distance} ${from.y}, ${to.x - distance} ${to.y}, ${to.x} ${to.y}`;
	}

	function beginDrag(event: PointerEvent, tableId: string) {
		event.stopPropagation();
		const position = positions[tableId];
		if (!position) return;
		const canvasRect = (
			(event.currentTarget as HTMLElement).parentElement as HTMLElement
		).getBoundingClientRect();

		dragState = {
			tableId,
			offsetX: (event.clientX - canvasRect.left) / zoom - position.x,
			offsetY: (event.clientY - canvasRect.top) / zoom - position.y,
			pointerId: event.pointerId,
			startX: event.clientX,
			startY: event.clientY
		};
		dragMoved = false;
		clearTooltipTimeout();
		tooltip = null;

		(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
	}

	function dragTable(event: PointerEvent) {
		if (!dragState || event.pointerId !== dragState.pointerId) return;
		const canvas = (event.currentTarget as HTMLElement).parentElement;
		if (!canvas) return;
		const canvasRect = canvas.getBoundingClientRect();

		const dx = Math.abs(event.clientX - dragState.startX);
		const dy = Math.abs(event.clientY - dragState.startY);
		if (dx > 3 || dy > 3) {
			dragMoved = true;
		}

		positions = {
			...positions,
			[dragState.tableId]: {
				x: Math.max(8, (event.clientX - canvasRect.left) / zoom - dragState.offsetX),
				y: Math.max(8, (event.clientY - canvasRect.top) / zoom - dragState.offsetY)
			}
		};
		userMovedLayout = true;
	}

	function endDrag(event: PointerEvent) {
		if (!dragState || event.pointerId !== dragState.pointerId) return;
		dragState = null;
	}

	function beginPan(event: PointerEvent) {
		if (!schemaScrollEl) return;
		if ((event.target as HTMLElement).closest('.schema-table')) return;

		panState = {
			pointerId: event.pointerId,
			startX: event.clientX,
			startY: event.clientY,
			startScrollLeft: schemaScrollEl.scrollLeft,
			startScrollTop: schemaScrollEl.scrollTop
		};
		isPanning = true;
		schemaScrollEl.setPointerCapture(event.pointerId);
	}

	function pan(event: PointerEvent) {
		if (!panState || event.pointerId !== panState.pointerId || !schemaScrollEl) return;
		schemaScrollEl.scrollLeft = panState.startScrollLeft - (event.clientX - panState.startX);
		schemaScrollEl.scrollTop = panState.startScrollTop - (event.clientY - panState.startY);
	}

	function endPan(event: PointerEvent) {
		if (!panState || event.pointerId !== panState.pointerId || !schemaScrollEl) return;
		if (schemaScrollEl.hasPointerCapture(event.pointerId)) {
			schemaScrollEl.releasePointerCapture(event.pointerId);
		}
		panState = null;
		isPanning = false;
	}

	function handleTableClick(tableId: string) {
		if (dragMoved) return;
		openSidebar(tableId);
	}

	async function openSidebar(tableId: string) {
		selectedTableId = tableId;
		sidebarOpen = true;
		historyLoading = true;
		historyError = '';
		historyItems = [];

		if (!selectedDb) return;

		try {
			const response = await getDatabaseSchemaHistory(selectedDb.id, tableId, 100, 0);
			historyItems = response.items;
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			historyError = err.message || 'Failed to load table history.';
		} finally {
			historyLoading = false;
		}
	}

	function closeSidebar() {
		sidebarOpen = false;
		selectedTableId = null;
		historyItems = [];
		historyError = '';
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape' && sidebarOpen) {
			closeSidebar();
		}
	}

	function resetLayout() {
		if (!schema) return;
		userMovedLayout = false;
		positions = createInitialPositions(schema.tables, selectedSchema);
		centerBoard();
	}

	function selectSchema(schemaName: string) {
		selectedSchema = schemaName;
		if (!schema) return;
		userMovedLayout = false;
		positions = createInitialPositions(schema.tables, selectedSchema);
		centerBoard();
	}

	async function centerBoard() {
		await tick();
		if (!schemaScrollEl) return;
		const bounds = getDiagramBounds(visibleTables, positions);
		if (!bounds) return;

		const diagramCenter = ((bounds.minX + bounds.maxX) / 2) * zoom + worldOffsetX;

		schemaScrollEl.scrollTo({
			left: Math.max(0, diagramCenter - schemaScrollEl.clientWidth / 2),
			top: 0,
			behavior: 'instant'
		});
	}

	function zoomBy(delta: number) {
		zoom = Math.min(maxZoom, Math.max(minZoom, Number((zoom + delta).toFixed(2))));
		if (!userMovedLayout) {
			centerBoard();
		}
	}

	function getDiagramBounds(schemaTables: SchemaTable[], tablePositions: Record<string, Position>) {
		if (schemaTables.length === 0) return null;

		let minX = Number.POSITIVE_INFINITY;
		let maxX = Number.NEGATIVE_INFINITY;

		for (const table of schemaTables) {
			const position = tablePositions[table.id];
			if (!position) continue;
			minX = Math.min(minX, position.x);
			maxX = Math.max(maxX, position.x + tableWidth);
		}

		if (!Number.isFinite(minX) || !Number.isFinite(maxX)) return null;
		return { minX, maxX };
	}

	function handleWheel(event: WheelEvent) {
		if (!event.ctrlKey && !event.metaKey) return;
		event.preventDefault();

		const nextZoom = Math.min(
			maxZoom,
			Math.max(minZoom, Number((zoom + (event.deltaY > 0 ? -0.08 : 0.08)).toFixed(2)))
		);
		if (nextZoom === zoom || !schemaScrollEl) return;

		const rect = schemaScrollEl.getBoundingClientRect();
		const mouseX = event.clientX - rect.left;
		const mouseY = event.clientY - rect.top;

		const worldX = (mouseX + schemaScrollEl.scrollLeft - worldOffsetX) / zoom;
		const worldY = (mouseY + schemaScrollEl.scrollTop) / zoom;

		zoom = nextZoom;

		const nextScaledCanvasWidth = canvasSize.width * nextZoom;
		const nextWorldOffsetX = Math.max(0, (boardViewportWidth - nextScaledCanvasWidth) / 2);
		const nextScrollLeft = worldX * nextZoom + nextWorldOffsetX - mouseX;
		const nextScrollTop = worldY * nextZoom - mouseY;

		schemaScrollEl.scrollTo({
			left: Math.max(0, nextScrollLeft),
			top: Math.max(0, nextScrollTop),
			behavior: 'instant'
		});
	}

	function fkLabel(column: SchemaColumn): string {
		const fkTable = column.fk_table_id ? tableById.get(column.fk_table_id) : null;
		const fkColumn = column.fk_column_id ? columnById.get(column.fk_column_id) : null;
		if (!fkTable) return '';
		return `${fkTable.schema_name}.${fkTable.name}${fkColumn ? `.${fkColumn.name}` : ''}`;
	}

	function historyTypeIcon(type: SchemaHistoryItem['type']): string {
		if (type === 'table') return 'table_chart';
		if (type === 'column') return 'view_column';
		return 'tag';
	}

	function historyActionClass(action: SchemaHistoryItem['action']): string {
		if (action === 'added') return 'bg-success-container text-on-success-container';
		if (action === 'removed') return 'bg-error-container text-on-error-container';
		return 'bg-tertiary-container text-on-tertiary-container';
	}

	function formatHistoryDate(iso: string): string {
		const date = new Date(iso);
		return date.toLocaleString();
	}

	function clearTooltipTimeout() {
		if (tooltipTimeout) {
			clearTimeout(tooltipTimeout);
			tooltipTimeout = null;
		}
	}

	function handleTableMouseEnter(event: MouseEvent, table: SchemaTable) {
		if (!table.description) return;
		clearTooltipTimeout();
		tooltipTimeout = setTimeout(() => {
			tooltip = { text: table.description!, x: event.clientX, y: event.clientY - 12 };
		}, 400);
	}

	function handleTableMouseMove(event: MouseEvent) {
		if (tooltip) {
			tooltip = { ...tooltip, x: event.clientX, y: event.clientY - 12 };
		}
	}

	function handleTableMouseLeave() {
		clearTooltipTimeout();
		tooltip = null;
	}

	onMount(() => {
		loadDatabases();
	});
</script>

<svelte:window onkeydown={handleKeyDown} />

<header
	class="fixed top-0 right-0 z-40 flex h-16 w-[calc(100%-16rem)] items-center justify-between border-b border-outline-variant bg-surface-dim px-container-padding"
>
	<div class="flex items-center gap-4">
		<span class="material-symbols-outlined text-primary">account_tree</span>
		<div class="flex items-center gap-3">
			<h1 class="m-0 font-headline-md text-headline-md text-on-background">Schema</h1>
			<div class="relative">
				<button
					onclick={() => (schemaHelpOpen = !schemaHelpOpen)}
					onmouseenter={() => (schemaHelpOpen = true)}
					onmouseleave={() => (schemaHelpOpen = false)}
					class="flex h-6 w-6 cursor-pointer items-center justify-center rounded-full border border-outline-variant text-on-surface-variant transition-colors hover:border-primary/40 hover:text-primary"
					aria-label="Schema page explanation"
				>
					<span class="material-symbols-outlined text-[14px]">help</span>
				</button>
				{#if schemaHelpOpen}
					<div
						class="absolute left-0 top-full z-50 mt-2 w-80 rounded-lg border border-outline-variant bg-surface-container-high p-3 text-xs text-on-surface shadow-lg"
					>
						<p class="mb-1 font-bold">What is this page?</p>
						<p class="mb-2 text-on-surface-variant">
							Visual entity-relationship map of the selected database. Pan the board by dragging the
							background, arrange tables by dragging them, and use Ctrl + wheel to zoom.
						</p>
						<p class="font-bold">Table details</p>
						<p class="text-on-surface-variant">
							Click any table to open its details panel, showing schema changes and, soon, pgwarden
							documentation stored for that table.
						</p>
					</div>
				{/if}
			</div>
			{#if selectedDb}
				<span class="font-label-caps text-[10px] text-on-surface-variant">{selectedDb.name}</span>
			{/if}
		</div>
	</div>
	<div class="flex items-center gap-2">
		{#if schema}
			<span
				class="rounded-full border border-outline-variant bg-surface-container px-3 py-1 font-label-caps text-[10px] text-on-surface-variant"
			>
				{visibleTables.length} of {tables.length} tables / {foreignKeyLinks.length} FK
			</span>
		{/if}
		<button
			onclick={() => zoomBy(-0.1)}
			disabled={!schema || zoom <= minZoom}
			class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border border-outline-variant bg-surface-container text-on-surface-variant transition-colors hover:bg-surface-variant disabled:cursor-not-allowed disabled:opacity-50"
			title="Zoom out"
		>
			<span class="material-symbols-outlined text-[18px]">remove</span>
		</button>
		<span class="w-12 text-center font-code-sm text-code-sm text-on-surface-variant"
			>{Math.round(zoom * 100)}%</span
		>
		<button
			onclick={() => zoomBy(0.1)}
			disabled={!schema || zoom >= maxZoom}
			class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg border border-outline-variant bg-surface-container text-on-surface-variant transition-colors hover:bg-surface-variant disabled:cursor-not-allowed disabled:opacity-50"
			title="Zoom in"
		>
			<span class="material-symbols-outlined text-[18px]">add</span>
		</button>
	</div>
</header>

<div class="px-container-padding pb-10 pt-24">
	{#if loading}
		<div class="flex items-center justify-center py-12">
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
	{:else if databases.length === 0}
		<div class="flex flex-col items-center justify-center py-24">
			<div
				class="mb-6 flex h-20 w-20 items-center justify-center rounded-xl border border-outline-variant bg-surface-container-high"
			>
				<span class="material-symbols-outlined text-[40px] text-on-surface-variant"
					>database_off</span
				>
			</div>
			<h2 class="mb-2 font-headline-md text-headline-md font-bold text-on-surface">
				No databases connected
			</h2>
			<p class="mb-8 max-w-md text-center text-body-md text-on-surface-variant">
				Connect a database from the Overview page to inspect its schema map.
			</p>
			<a
				href="/overview"
				class="flex cursor-pointer items-center gap-2 rounded-lg bg-primary px-8 py-3 text-sm font-bold text-on-primary"
			>
				<span class="material-symbols-outlined text-sm">dashboard</span>
				Go to Overview
			</a>
		</div>
	{:else}
		<div class="mb-6 flex flex-wrap items-center justify-between gap-4">
			<div class="flex flex-wrap items-center gap-3">
				<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant"
					>Database</span
				>
				{#each databases as db}
					<button
						onclick={() => selectDatabase(db)}
						disabled={schemaLoading}
						class="cursor-pointer rounded-lg px-3 py-1.5 text-xs font-bold transition-all disabled:cursor-not-allowed disabled:opacity-60 {selectedDb?.id ===
						db.id
							? 'bg-primary text-on-primary'
							: 'border border-outline-variant bg-surface-container text-on-surface-variant hover:bg-surface-variant'}"
					>
						{db.name}
					</button>
				{/each}
			</div>
		</div>

		{#if schema}
			<div class="mb-6 grid gap-3 lg:grid-cols-[minmax(280px,1fr)_280px]">
				<label class="control-field">
					<span class="material-symbols-outlined text-[18px] text-on-surface-variant">search</span>
					<input
						bind:value={searchTerm}
						type="search"
						placeholder="Search table or schema"
						class="min-w-0 flex-1 bg-transparent font-body-md text-body-md text-on-surface outline-none placeholder:text-on-surface-variant"
					/>
					{#if searchTerm}
						<button
							onclick={() => (searchTerm = '')}
							class="flex h-6 w-6 cursor-pointer items-center justify-center rounded-md text-on-surface-variant hover:bg-surface-variant hover:text-on-surface"
							title="Clear search"
						>
							<span class="material-symbols-outlined text-[16px]">close</span>
						</button>
					{/if}
				</label>

				<label class="control-field">
					<span class="material-symbols-outlined text-[18px] text-on-surface-variant">segment</span>
					<select
						value={selectedSchema}
						onchange={(event) => selectSchema((event.currentTarget as HTMLSelectElement).value)}
						class="min-w-0 flex-1 cursor-pointer bg-transparent font-body-md text-body-md text-on-surface outline-none"
					>
						<option value="">All schemas</option>
						{#each schemaNames as schemaName}
							<option value={schemaName}>{schemaName}</option>
						{/each}
					</select>
				</label>
			</div>
		{/if}

		{#if error}
			<div
				class="mb-6 rounded-lg border border-error/30 bg-error-container/10 p-4 text-sm text-error"
			>
				{error}
			</div>
		{/if}

		<section class="overflow-hidden rounded-lg border border-outline-variant bg-surface-container">
			{#if schemaLoading}
				<div class="flex h-[520px] items-center justify-center">
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
			{:else if schema && tables.length === 0}
				<div class="flex h-[520px] flex-col items-center justify-center text-center">
					<span class="material-symbols-outlined mb-3 text-[40px] text-on-surface-variant"
						>table_chart_view</span
					>
					<p class="text-body-md text-on-surface-variant">
						No schema metadata collected for this database.
					</p>
				</div>
			{:else if schema && visibleTables.length === 0}
				<div class="flex h-[520px] flex-col items-center justify-center text-center">
					<span class="material-symbols-outlined mb-3 text-[40px] text-on-surface-variant"
						>search_off</span
					>
					<p class="text-body-md text-on-surface-variant">No tables match the current filters.</p>
				</div>
			{:else if schema}
				<div
					bind:this={schemaScrollEl}
					bind:clientWidth={boardViewportWidth}
					class="schema-scroll custom-scrollbar"
					class:panning={isPanning}
					role="application"
					aria-label="Schema diagram canvas"
					onwheel={handleWheel}
					onpointerdown={beginPan}
					onpointermove={pan}
					onpointerup={endPan}
					onpointercancel={endPan}
				>
					<div
						class="schema-canvas"
						style={`width: ${boardWidth}px; height: ${canvasSize.height * zoom}px;`}
					>
						<div
							class="schema-world"
							style={`width: ${canvasSize.width}px; height: ${canvasSize.height}px; transform: translateX(${worldOffsetX}px) scale(${zoom});`}
						>
							<svg class="schema-links" width={canvasSize.width} height={canvasSize.height}>
								<defs>
									<marker
										id="fk-arrow"
										markerWidth="10"
										markerHeight="10"
										refX="8"
										refY="3"
										orient="auto"
										markerUnits="strokeWidth"
									>
										<path d="M0,0 L0,6 L9,3 z" fill="var(--color-secondary-fixed-dim)" />
									</marker>
								</defs>
								{#each foreignKeyLinks as link (link.id)}
									<path class="fk-path" d={linkPath(link)} marker-end="url(#fk-arrow)" />
								{/each}
							</svg>

							{#each visibleTables as table (table.id)}
								{@const position = positions[table.id] ?? { x: 0, y: 0 }}
								<!-- svelte-ignore a11y_no_noninteractive_element_to_interactive_role -->
								<article
									class="schema-table {dragState?.tableId === table.id
										? 'dragging'
										: ''} {selectedSchema && table.schema_name === selectedSchema
										? 'schema-selected'
										: ''} {selectedTableId === table.id ? 'table-active' : ''}"
									style={`transform: translate(${position.x}px, ${position.y}px); width: ${tableWidth}px;`}
									role="button"
									tabindex="0"
									aria-label={`Open details for ${table.schema_name}.${table.name}`}
									onpointerdown={(event) => beginDrag(event, table.id)}
									onpointermove={dragTable}
									onpointerup={endDrag}
									onpointercancel={endDrag}
									onclick={() => handleTableClick(table.id)}
									onkeydown={(event) => {
										if (event.key === 'Enter' || event.key === ' ') {
											event.preventDefault();
											handleTableClick(table.id);
										}
									}}
									onmouseenter={(event) => handleTableMouseEnter(event, table)}
									onmousemove={handleTableMouseMove}
									onmouseleave={handleTableMouseLeave}
								>
									<div class="table-header">
										<div class="min-w-0">
											<div class="schema-name">{table.schema_name}</div>
											<h3 title={`${table.schema_name}.${table.name}`}>{table.name}</h3>
										</div>
										<span class="material-symbols-outlined table-grip">drag_indicator</span>
									</div>

									<div class="column-list">
										{#each table.columns as column (column.id)}
											<div class="column-row {column.fk_table_id ? 'has-fk' : ''}">
												<div class="min-w-0 flex-1">
													<div class="flex min-w-0 items-center gap-1.5">
														<span class="column-name" title={column.name}>{column.name}</span>
														{#if table.indexes.some((index) => index.is_primary && index.columns.includes(column.name))}
															<span class="column-pill primary">PK</span>
														{/if}
														{#if column.fk_table_id}
															<span class="column-pill fk" title={fkLabel(column)}>FK</span>
														{/if}
														{#if column.is_unique}
															<span class="column-pill unique">UQ</span>
														{/if}
													</div>
													{#if column.default_value}
														<div class="column-default" title={column.default_value}>
															default {column.default_value}
														</div>
													{/if}
												</div>
												<div class="column-meta">
													<span title={column.data_type}>{column.data_type}</span>
													<strong class={column.is_nullable ? 'nullable' : 'required'}>
														{column.is_nullable ? 'null' : 'not null'}
													</strong>
												</div>
											</div>
										{/each}
									</div>

									{#if table.indexes.length > 0}
										<div class="index-strip">
											<span class="material-symbols-outlined text-[14px] text-secondary-fixed-dim"
												>tag</span
											>
											<span>{table.indexes.length} indexes</span>
										</div>
									{/if}
								</article>
							{/each}
						</div>
					</div>
				</div>
			{/if}
		</section>
	{/if}
</div>

{#if sidebarOpen && selectedTable}
	<div class="fixed inset-0 z-40 bg-black/20" onclick={closeSidebar} aria-hidden="true"></div>
	<!-- svelte-ignore a11y_no_noninteractive_element_to_interactive_role -->
	<aside
		class="fixed top-16 right-0 z-50 flex h-[calc(100%-4rem)] w-96 flex-col border-l border-outline-variant bg-surface-container-low shadow-2xl"
		role="dialog"
		aria-modal="true"
		aria-labelledby="sidebar-title"
	>
		<div
			class="flex items-center justify-between border-b border-outline-variant bg-surface-container px-4 py-3"
		>
			<div class="min-w-0 flex-1">
				<div class="text-[10px] font-label-caps uppercase tracking-widest text-primary">
					{selectedTable.schema_name}
				</div>
				<h2
					id="sidebar-title"
					class="truncate font-headline-md text-headline-md font-bold text-on-surface"
				>
					{selectedTable.name}
				</h2>
			</div>
			<button
				onclick={closeSidebar}
				class="ml-2 flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-variant hover:text-on-surface"
				aria-label="Close sidebar"
			>
				<span class="material-symbols-outlined text-[20px]">close</span>
			</button>
		</div>

		<div class="custom-scrollbar flex-1 overflow-y-auto p-4">
			{#if historyLoading}
				<div class="flex items-center justify-center py-12">
					<svg
						class="h-6 w-6 animate-spin text-primary"
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
			{:else if historyError}
				<div class="rounded-lg border border-error/30 bg-error-container/10 p-3 text-xs text-error">
					{historyError}
				</div>
			{:else if historyItems.length === 0}
				<div class="flex flex-col items-center justify-center py-12 text-center">
					<span class="material-symbols-outlined mb-2 text-[32px] text-on-surface-variant"
						>history_toggle_off</span
					>
					<p class="text-body-md text-on-surface-variant">No changes recorded for this table.</p>
				</div>
			{:else}
				<ul class="space-y-3">
					{#each historyItems as item (item.id)}
						<li class="rounded-lg border border-outline-variant/50 bg-surface-container p-3">
							<div class="mb-1 flex items-center gap-2">
								<span class="material-symbols-outlined text-[18px] text-on-surface-variant">
									{historyTypeIcon(item.type)}
								</span>
								<span
									class="text-[10px] font-label-caps uppercase tracking-wider text-on-surface-variant"
								>
									{item.type}
								</span>
								<span
									class="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase {historyActionClass(
										item.action
									)}"
								>
									{item.action}
								</span>
							</div>
							{#if item.column_name || item.index_name}
								<div class="mb-1 truncate font-mono text-xs text-on-surface">
									{item.column_name || item.index_name}
								</div>
							{/if}
							<p class="text-body-sm text-body-sm text-on-surface-variant">
								{item.details}
							</p>
							<time class="mt-1 block text-[10px] text-on-surface-variant/70">
								{formatHistoryDate(item.changed_at)}
							</time>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</aside>
{/if}

{#if tooltip}
	<div
		class="fixed z-50 max-w-xs rounded-lg border border-outline-variant bg-inverse-surface px-3 py-2 text-xs text-inverse-on-surface shadow-lg pointer-events-none"
		style={`left: ${tooltip.x}px; top: ${tooltip.y}px; transform: translate(-50%, -100%);`}
	>
		{tooltip.text}
	</div>
{/if}

<style>
	.control-field {
		align-items: center;
		background: var(--color-surface-container);
		border: 1px solid var(--color-outline-variant);
		border-radius: 8px;
		display: flex;
		gap: 10px;
		min-height: 42px;
		padding: 0 12px;
	}

	.control-field:focus-within {
		border-color: var(--color-primary);
		box-shadow: 0 0 0 2px rgba(79, 219, 200, 0.12);
	}

	.control-field select option {
		background: var(--color-surface-container);
		color: var(--color-on-surface);
	}

	.schema-scroll {
		cursor: grab;
		height: calc(100vh - 190px);
		min-height: 560px;
		overflow: auto;
		background:
			linear-gradient(var(--color-outline-variant) 1px, transparent 1px),
			linear-gradient(90deg, var(--color-outline-variant) 1px, transparent 1px),
			var(--color-surface-container-lowest);
		background-size: 32px 32px;
		background-position: -1px -1px;
	}

	.schema-scroll.panning {
		cursor: grabbing;
		user-select: none;
	}

	.schema-scroll.panning .schema-table {
		cursor: grabbing;
	}

	.schema-canvas {
		position: relative;
	}

	.schema-world {
		left: 0;
		position: absolute;
		top: 0;
		transform-origin: 0 0;
	}

	.schema-links {
		inset: 0;
		overflow: visible;
		pointer-events: none;
		position: absolute;
	}

	.fk-path {
		fill: none;
		opacity: 0.78;
		stroke: var(--color-secondary-fixed-dim);
		stroke-linecap: round;
		stroke-width: 2;
	}

	.schema-table {
		background: var(--color-surface-container);
		border: 1px solid var(--color-outline-variant);
		border-radius: 8px;
		box-shadow: 0 14px 36px rgba(0, 0, 0, 0.28);
		cursor: pointer;
		overflow: hidden;
		position: absolute;
		touch-action: none;
		user-select: none;
	}

	.schema-table:hover {
		border-color: var(--color-primary);
	}

	.schema-table.dragging {
		border-color: var(--color-primary);
		box-shadow: 0 18px 48px rgba(79, 219, 200, 0.2);
		cursor: grabbing;
		z-index: 10;
	}

	.schema-table.schema-selected {
		border-color: var(--color-primary);
		box-shadow:
			0 0 0 2px rgba(79, 219, 200, 0.16),
			0 18px 48px rgba(79, 219, 200, 0.16);
	}

	.schema-table.schema-selected .table-header {
		background: linear-gradient(
			135deg,
			rgba(79, 219, 200, 0.16),
			var(--color-surface-container-high)
		);
	}

	.schema-table.table-active {
		border-color: var(--color-primary);
		box-shadow:
			0 0 0 3px rgba(79, 219, 200, 0.22),
			0 18px 48px rgba(79, 219, 200, 0.2);
	}

	.table-header {
		align-items: center;
		background: var(--color-surface-container-high);
		border-bottom: 1px solid var(--color-outline-variant);
		display: flex;
		justify-content: space-between;
		min-height: 62px;
		padding: 11px 14px;
	}

	.schema-name {
		color: var(--color-primary);
		font-family: 'JetBrains Mono', monospace;
		font-size: 10px;
		line-height: 14px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	h3 {
		color: var(--color-on-surface);
		font-size: 16px;
		font-weight: 700;
		line-height: 22px;
		margin: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.table-grip {
		color: var(--color-on-surface-variant);
		font-size: 20px;
		flex: 0 0 auto;
	}

	.column-list {
		background: var(--color-surface-container);
	}

	.column-row {
		align-items: center;
		border-bottom: 1px solid rgba(60, 73, 71, 0.45);
		display: flex;
		gap: 8px;
		min-height: 36px;
		padding: 6px 12px;
	}

	.column-row.has-fk {
		background: rgba(185, 199, 224, 0.06);
	}

	.column-name {
		color: var(--color-on-surface);
		display: block;
		font-family: 'JetBrains Mono', monospace;
		font-size: 12px;
		line-height: 16px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.column-meta {
		align-items: flex-end;
		color: var(--color-on-surface-variant);
		display: flex;
		flex: 0 0 144px;
		flex-direction: column;
		font-family: 'JetBrains Mono', monospace;
		font-size: 10px;
		line-height: 14px;
		min-width: 0;
	}

	.column-meta span {
		max-width: 144px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.column-meta strong {
		font-size: 9px;
		font-weight: 700;
		text-transform: uppercase;
	}

	.nullable {
		color: var(--color-tertiary);
	}

	.required {
		color: var(--color-primary);
	}

	.column-default {
		color: var(--color-on-surface-variant);
		font-family: 'JetBrains Mono', monospace;
		font-size: 10px;
		line-height: 14px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.column-pill {
		border-radius: 4px;
		flex: 0 0 auto;
		font-size: 9px;
		font-weight: 800;
		line-height: 12px;
		padding: 1px 4px;
	}

	.column-pill.primary {
		background: rgba(79, 219, 200, 0.14);
		color: var(--color-primary);
	}

	.column-pill.fk {
		background: rgba(185, 199, 224, 0.14);
		color: var(--color-secondary-fixed);
	}

	.column-pill.unique {
		background: rgba(255, 181, 158, 0.12);
		color: var(--color-tertiary);
	}

	.index-strip {
		align-items: center;
		color: var(--color-on-surface-variant);
		display: flex;
		font-size: 11px;
		gap: 6px;
		height: 42px;
		padding: 0 12px;
	}
</style>
