<script lang="ts">
	import { onMount } from 'svelte';
	import {
		listNotifications,
		setNotificationHidden,
		type NotificationItem,
		type NotificationLevel
	} from '$lib/notifications';

	let {
		open,
		collapsed,
		onClose,
		onCountChange
	}: {
		open: boolean;
		collapsed: boolean;
		onClose: () => void;
		onCountChange: (count: number) => void;
	} = $props();

	let notifications = $state<NotificationItem[]>([]);
	let visibility = $state<'active' | 'hidden'>('active');
	let level = $state<'all' | NotificationLevel>('all');
	let total = $state(0);
	let visibleCount = $state(0);
	let hiddenCount = $state(0);
	let levelCounts = $state<Record<NotificationLevel, number>>({
		critical: 0,
		warning: 0,
		info: 0
	});
	let loading = $state(true);
	let error = $state('');
	let updatingId = $state<number | null>(null);
	let requestSequence = 0;

	async function loadNotifications() {
		const sequence = ++requestSequence;
		loading = true;
		error = '';
		try {
			const response = await listNotifications({
				hidden: visibility === 'hidden',
				level: level === 'all' ? undefined : level
			});
			if (sequence !== requestSequence) return;
			notifications = response.items;
			total = response.total;
			visibleCount = response.visible_count;
			hiddenCount = response.hidden_count;
			levelCounts = response.level_counts;
			onCountChange(response.visible_count);
		} catch (loadError) {
			if (sequence !== requestSequence) return;
			error = loadError instanceof Error ? loadError.message : 'Unable to load notifications.';
		} finally {
			if (sequence === requestSequence) loading = false;
		}
	}

	async function toggleHidden(notification: NotificationItem) {
		updatingId = notification.id;
		error = '';
		try {
			await setNotificationHidden(notification.id, !notification.hidden);
			await loadNotifications();
		} catch (updateError) {
			error = updateError instanceof Error ? updateError.message : 'Unable to update notification.';
		} finally {
			updatingId = null;
		}
	}

	function notificationLevel(notification: NotificationItem): NotificationLevel {
		const severity = notification.params.severity;
		return severity === 'critical' || severity === 'warning' ? severity : 'info';
	}

	function levelIcon(notificationLevel: NotificationLevel): string {
		if (notificationLevel === 'critical') return 'error';
		if (notificationLevel === 'warning') return 'warning';
		return 'info';
	}

	function levelClasses(notificationLevel: NotificationLevel): string {
		if (notificationLevel === 'critical') {
			return 'border-status-danger/50 bg-status-danger/10 text-status-danger';
		}
		if (notificationLevel === 'warning') {
			return 'border-status-warning/50 bg-status-warning/10 text-status-warning';
		}
		return 'border-status-info/50 bg-status-info/10 text-status-info';
	}

	function sourceLabel(notification: NotificationItem): string {
		const source = notification.params.source ?? notification.params.scope ?? 'system';
		return String(source).replaceAll('_', ' ');
	}

	function notificationPath(notification: NotificationItem): string | null {
		const path = notification.params.path;
		return typeof path === 'string' && path.startsWith('/') ? path : null;
	}

	function formatTimestamp(timestamp: string): string {
		return new Intl.DateTimeFormat(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		}).format(new Date(timestamp));
	}

	function selectVisibility(nextVisibility: 'active' | 'hidden') {
		visibility = nextVisibility;
		level = 'all';
	}

	onMount(() => {
		void loadNotifications();
		const refreshTimer = window.setInterval(() => void loadNotifications(), 30_000);
		return () => window.clearInterval(refreshTimer);
	});

	$effect(() => {
		open;
		visibility;
		level;
		if (open) void loadNotifications();
	});
</script>

{#if open}
	<section
		aria-label="Notifications"
		class="fixed top-0 z-30 flex h-screen w-96 flex-col border-r border-surface-border bg-surface-container-low shadow-2xl transition-[left] duration-300"
		style:left={collapsed ? '4rem' : '16rem'}
	>
		<header class="flex items-center justify-between border-b border-surface-border px-5 py-4">
			<div>
				<h2 class="m-0 font-headline-md text-lg font-bold text-on-surface">Notifications</h2>
				<p class="mt-1 text-xs text-on-surface-variant">
					{visibleCount} active · {hiddenCount} hidden
				</p>
			</div>
			<button
				type="button"
				onclick={onClose}
				class="flex h-9 w-9 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface"
				aria-label="Close notifications"
				title="Close notifications"
			>
				<span class="material-symbols-outlined text-[20px]">close</span>
			</button>
		</header>

		<div class="space-y-3 border-b border-surface-border px-4 py-3">
			<div class="grid grid-cols-2 gap-1 rounded-lg bg-surface-container p-1">
				<button
					type="button"
					onclick={() => selectVisibility('active')}
					class="rounded-md px-3 py-2 text-xs font-semibold transition-colors {visibility ===
					'active'
						? 'bg-primary-container text-on-primary-container'
						: 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'}"
				>
					Active <span class="ml-1 opacity-70">{visibleCount}</span>
				</button>
				<button
					type="button"
					onclick={() => selectVisibility('hidden')}
					class="rounded-md px-3 py-2 text-xs font-semibold transition-colors {visibility ===
					'hidden'
						? 'bg-primary-container text-on-primary-container'
						: 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'}"
				>
					Hidden <span class="ml-1 opacity-70">{hiddenCount}</span>
				</button>
			</div>

			<div class="flex gap-2 overflow-x-auto pb-1">
				<button
					type="button"
					onclick={() => (level = 'all')}
					class="shrink-0 rounded-full border px-3 py-1.5 text-[11px] font-semibold transition-colors {level ===
					'all'
						? 'border-primary bg-primary/15 text-primary'
						: 'border-surface-border text-on-surface-variant hover:border-outline hover:text-on-surface'}"
				>
					All {Object.values(levelCounts).reduce((sum, count) => sum + count, 0)}
				</button>
				{#each ['critical', 'warning', 'info'] as notificationLevel}
					<button
						type="button"
						onclick={() => (level = notificationLevel as NotificationLevel)}
						class="shrink-0 rounded-full border px-3 py-1.5 text-[11px] font-semibold capitalize transition-all hover:-translate-y-px {level ===
						notificationLevel
							? levelClasses(notificationLevel as NotificationLevel)
							: 'border-surface-border text-on-surface-variant hover:border-outline hover:text-on-surface'}"
					>
						{notificationLevel}
						{levelCounts[notificationLevel as NotificationLevel]}
					</button>
				{/each}
			</div>
		</div>

		<div class="custom-scrollbar flex-1 overflow-y-auto p-3">
			{#if error}
				<div
					class="mb-3 rounded-lg border border-error/40 bg-error-container/20 p-3 text-xs text-error"
				>
					<p>{error}</p>
					<button
						type="button"
						onclick={loadNotifications}
						class="mt-2 font-semibold underline underline-offset-2 hover:text-on-error-container"
					>
						Try again
					</button>
				</div>
			{/if}

			{#if loading}
				<div class="flex h-40 items-center justify-center text-on-surface-variant">
					<span class="material-symbols-outlined animate-spin">progress_activity</span>
				</div>
			{:else if notifications.length === 0}
				<div class="flex h-52 flex-col items-center justify-center px-8 text-center">
					<span class="material-symbols-outlined mb-3 text-4xl text-outline">notifications_off</span
					>
					<p class="font-semibold text-on-surface">No {visibility} notifications</p>
					<p class="mt-1 text-xs text-on-surface-variant">
						{level === 'all'
							? 'New events will appear here.'
							: `There are no ${level} events in this view.`}
					</p>
				</div>
			{:else}
				<div class="space-y-2">
					{#each notifications as notification (notification.id)}
						{@const itemLevel = notificationLevel(notification)}
						{@const path = notificationPath(notification)}
						<article
							class="group rounded-xl border border-surface-border bg-surface-container p-3 transition-all hover:-translate-y-px hover:border-outline hover:bg-surface-container-high hover:shadow-lg"
						>
							<div class="flex gap-3">
								<div
									class="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border {levelClasses(
										itemLevel
									)}"
								>
									<span class="material-symbols-outlined text-[18px]">{levelIcon(itemLevel)}</span>
								</div>
								<div class="min-w-0 flex-1">
									<div class="mb-1 flex items-start justify-between gap-2">
										<span
											class="text-[10px] font-bold uppercase tracking-wider {itemLevel ===
											'critical'
												? 'text-status-danger'
												: itemLevel === 'warning'
													? 'text-status-warning'
													: 'text-status-info'}"
										>
											{itemLevel} · {sourceLabel(notification)}
										</span>
										<button
											type="button"
											onclick={() => toggleHidden(notification)}
											disabled={updatingId === notification.id}
											class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-on-surface-variant opacity-0 transition-all hover:bg-surface-variant hover:text-primary focus:opacity-100 disabled:cursor-wait disabled:opacity-50 group-hover:opacity-100"
											aria-label={notification.hidden
												? 'Restore notification'
												: 'Hide notification'}
											title={notification.hidden ? 'Restore notification' : 'Hide notification'}
										>
											<span class="material-symbols-outlined text-[17px]">
												{updatingId === notification.id
													? 'progress_activity'
													: notification.hidden
														? 'visibility'
														: 'visibility_off'}
											</span>
										</button>
									</div>
									{#if path}
										<a
											href={path}
											onclick={onClose}
											class="block text-sm leading-5 text-on-surface transition-colors hover:text-primary"
										>
											{notification.message}
										</a>
									{:else}
										<p class="text-sm leading-5 text-on-surface">{notification.message}</p>
									{/if}
									<time
										datetime={notification.created_at}
										class="mt-2 block font-code-sm text-[10px] text-on-surface-variant"
									>
										{formatTimestamp(notification.created_at)}
									</time>
								</div>
							</div>
						</article>
					{/each}
				</div>
			{/if}
		</div>

		<footer
			class="border-t border-surface-border px-4 py-3 text-center text-[10px] text-on-surface-variant"
		>
			Showing {notifications.length} of {total}
		</footer>
	</section>
{/if}
