<script lang="ts">
	import { onMount } from 'svelte';
	import {
		listNotifierChannels,
		patchNotifierChannel,
		type NotifierChannel
	} from '$lib/api';

	type CredentialField = {
		key: string;
		label: string;
		type: 'text' | 'password' | 'number';
	};

	const channelMeta: Record<string, { icon: string; description: string; fields: CredentialField[] }> = {
		slack: {
			icon: 'tag',
			description: 'Send alerts to a Slack channel via incoming webhook.',
			fields: [{ key: 'webhook_url', label: 'Webhook URL', type: 'password' }]
		},
		discord: {
			icon: 'forum',
			description: 'Send alerts to a Discord channel via webhook.',
			fields: [{ key: 'webhook_url', label: 'Webhook URL', type: 'password' }]
		},
		teams: {
			icon: 'groups',
			description: 'Send alerts to a Microsoft Teams channel via webhook.',
			fields: [{ key: 'webhook_url', label: 'Webhook URL', type: 'password' }]
		},
		email: {
			icon: 'mail',
			description: 'Send alerts by email through an SMTP server.',
			fields: [
				{ key: 'host', label: 'SMTP host', type: 'text' },
				{ key: 'port', label: 'SMTP port', type: 'number' },
				{ key: 'username', label: 'Username', type: 'text' },
				{ key: 'password', label: 'Password', type: 'password' },
				{ key: 'from', label: 'From', type: 'text' },
				{ key: 'to', label: 'To', type: 'text' }
			]
		}
	};

	type ChannelDraft = {
		enabled: boolean;
		fields: Record<string, string>;
	};

	let channels = $state<NotifierChannel[]>([]);
	let drafts = $state<Record<number, ChannelDraft>>({});
	let loading = $state(true);
	let savingId = $state<number | null>(null);
	let error = $state('');
	let savedId = $state<number | null>(null);

	function metaFor(channel: NotifierChannel) {
		return (
			channelMeta[channel.name] ?? {
				icon: 'notifications',
				description: 'Notification channel.',
				fields: []
			}
		);
	}

	function toDraft(channel: NotifierChannel): ChannelDraft {
		return {
			enabled: channel.enabled,
			fields: Object.fromEntries(metaFor(channel).fields.map((field) => [field.key, '']))
		};
	}

	async function load() {
		try {
			loading = true;
			error = '';
			channels = await listNotifierChannels();
			drafts = Object.fromEntries(channels.map((channel) => [channel.id, toDraft(channel)]));
		} catch (err: any) {
			handleError(err, 'Failed to load notification channels.');
		} finally {
			loading = false;
		}
	}

	function updateDraftEnabled(channelId: number, enabled: boolean) {
		const channel = channels.find((item) => item.id === channelId);
		if (!channel) return;
		const current = drafts[channelId] ?? toDraft(channel);
		drafts = { ...drafts, [channelId]: { ...current, enabled } };
	}

	function updateDraftField(channelId: number, key: string, value: string) {
		const channel = channels.find((item) => item.id === channelId);
		if (!channel) return;
		const current = drafts[channelId] ?? toDraft(channel);
		drafts = {
			...drafts,
			[channelId]: { ...current, fields: { ...current.fields, [key]: value } }
		};
	}

	function isDirty(channel: NotifierChannel): boolean {
		const draft = drafts[channel.id];
		if (!draft) return false;
		if (draft.enabled !== channel.enabled) return true;
		return Object.values(draft.fields).some((value) => value.trim().length > 0);
	}

	async function saveChannel(channel: NotifierChannel) {
		const draft = drafts[channel.id];
		if (!draft || !isDirty(channel)) return;

		try {
			savingId = channel.id;
			error = '';
			savedId = null;

			const patch: { enabled?: boolean; credentials?: Record<string, string | number> } = {};
			if (draft.enabled !== channel.enabled) {
				patch.enabled = draft.enabled;
			}

			const filledFields = Object.fromEntries(
				Object.entries(draft.fields).filter(([, value]) => value.trim().length > 0)
			);
			if (Object.keys(filledFields).length > 0) {
				const portField = metaFor(channel).fields.find((field) => field.type === 'number');
				patch.credentials = Object.fromEntries(
					Object.entries(filledFields).map(([key, value]) => [
						key,
						portField && key === portField.key ? Number(value) : value
					])
				);
			}

			await patchNotifierChannel(channel.id, patch);
			savedId = channel.id;
			await load();
		} catch (err: any) {
			handleError(err, 'Failed to update channel.');
		} finally {
			savingId = null;
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

	function formatName(name: string) {
		return name.replace(/_/g, ' ').replace(/^\w/, (char) => char.toUpperCase());
	}

	onMount(() => load());
</script>

<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex items-center px-container-padding h-16 gap-3"
>
	<span class="material-symbols-outlined text-on-surface-variant">notifications</span>
	<h1 class="font-headline-md text-headline-md text-on-background m-0">Alerts</h1>
	<span class="text-on-surface-variant">/</span>
	<span
		class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest"
		>Configuration</span
	>
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

	<section class="settings-card p-5">
		<div class="flex items-center gap-2 mb-1">
			<span class="material-symbols-outlined text-on-surface-variant text-[18px]">settings</span>
			<h2 class="font-bold text-on-surface text-base m-0">Notification channels</h2>
		</div>
		<p class="text-sm text-on-surface-variant">
			Enable channels and configure their credentials. Credentials are stored encrypted and are
			never displayed after saving.
		</p>
	</section>

	{#if loading}
		<div class="settings-card p-6 space-y-4">
			{#each [1, 2, 3] as _}
				<div class="skeleton h-16 w-full"></div>
			{/each}
		</div>
	{:else if channels.length === 0}
		<div class="settings-card px-6 py-12 flex flex-col items-center text-center">
			<span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3"
				>notifications_off</span
			>
			<p class="text-on-surface font-bold mb-1">No channels found</p>
			<p class="text-sm text-on-surface-variant">
				Channels are synced from the notifier configuration.
			</p>
		</div>
	{:else}
		{#each channels as channel (channel.id)}
			{@const meta = metaFor(channel)}
			{@const draft = drafts[channel.id] ?? toDraft(channel)}
			<section class="settings-card overflow-hidden">
				<div class="row-item px-5 py-4 flex flex-wrap items-center justify-between gap-4">
					<div class="flex items-center gap-3 min-w-0">
						<span class="material-symbols-outlined text-on-surface-variant text-[20px]"
							>{meta.icon}</span
						>
						<div class="min-w-0">
							<p class="font-bold text-on-surface text-sm truncate">{formatName(channel.name)}</p>
							<p class="text-xs text-on-surface-variant">{meta.description}</p>
						</div>
					</div>

					<div class="flex items-center gap-4 flex-shrink-0">
						{#if channel.has_credentials}
							<span
								class="flex items-center gap-1 text-xs text-on-surface-variant"
								title="Credentials configured"
							>
								<span class="material-symbols-outlined text-[16px] text-primary">key</span>
								Credentials set
							</span>
						{/if}
						<label class="flex items-center gap-2 text-xs font-bold text-on-surface">
							<input
								type="checkbox"
								checked={draft.enabled}
								disabled={savingId === channel.id}
								onchange={(event) =>
									updateDraftEnabled(channel.id, event.currentTarget.checked)}
								class="accent-primary"
							/>
							Active
						</label>
					</div>
				</div>

				{#if meta.fields.length > 0}
					<div class="row-item px-5 py-4 grid grid-cols-1 md:grid-cols-2 gap-4">
						{#each meta.fields as field}
							<div>
								<label
									class="text-xs text-on-surface-variant"
									for={`channel-${channel.id}-${field.key}`}>{field.label}</label
								>
								<input
									id={`channel-${channel.id}-${field.key}`}
									type={field.type}
									value={draft.fields[field.key] ?? ''}
									disabled={savingId === channel.id}
									placeholder={channel.has_credentials ? '••••••••' : ''}
									oninput={(event) =>
										updateDraftField(channel.id, field.key, event.currentTarget.value)}
									class="mt-1 w-full bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
								/>
							</div>
						{/each}
					</div>
				{/if}

				<div class="px-5 py-4 flex items-center justify-end gap-3">
					{#if savedId === channel.id}
						<span class="flex items-center gap-1 text-xs text-primary">
							<span class="material-symbols-outlined text-[16px]">check_circle</span>
							Saved
						</span>
					{/if}
					<button
						onclick={() => saveChannel(channel)}
						disabled={!isDirty(channel) || savingId === channel.id}
						class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold transition-all active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
					>
						<span class="material-symbols-outlined text-[18px]">save</span>
						{savingId === channel.id ? 'Saving...' : 'Save'}
					</button>
				</div>
			</section>
		{/each}
	{/if}
</div>

<style>
	.settings-card {
		background: rgba(26, 33, 31, 0.95);
		border: 1px solid rgba(133, 148, 144, 0.15);
		border-radius: 14px;
	}
	.row-item {
		border-bottom: 1px solid rgba(133, 148, 144, 0.08);
	}
	.row-item:last-child {
		border-bottom: none;
	}
	.skeleton {
		background: linear-gradient(
			90deg,
			rgba(133, 148, 144, 0.08) 25%,
			rgba(133, 148, 144, 0.16) 50%,
			rgba(133, 148, 144, 0.08) 75%
		);
		background-size: 200% 100%;
		animation: skeleton-shine 1.5s infinite;
		border-radius: 8px;
	}
	@keyframes skeleton-shine {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}
</style>
