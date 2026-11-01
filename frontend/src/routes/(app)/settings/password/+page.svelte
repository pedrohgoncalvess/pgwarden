<script lang="ts">
	import { apiFetch, authHeaders } from '$lib/auth';
	let currentPassword = $state('');
	let newPassword = $state('');
	let confirmation = $state('');
	let saving = $state(false);
	let error = $state('');
	let notice = $state('');

	async function save(event: SubmitEvent) {
		event.preventDefault();
		error = '';
		notice = '';
		if (newPassword !== confirmation) {
			error = 'The new password and confirmation must match.';
			return;
		}
		saving = true;
		try {
			const response = await apiFetch('/api/v1/auth/password', {
				method: 'POST',
				headers: authHeaders(),
				body: JSON.stringify({
					current_password: currentPassword,
					new_password: newPassword,
					confirm_password: confirmation
				})
			});
			if (!response.ok) {
				const body = await response.json().catch(() => ({}));
				const detail = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
				throw new Error(detail || 'Could not change your password.');
			}
			currentPassword = '';
			newPassword = '';
			confirmation = '';
			notice = 'Your password has been changed.';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not change your password.';
		} finally {
			saving = false;
		}
	}
</script>

<svelte:head><title>Change password · PGWarden</title></svelte:head>
<section class="mx-auto max-w-xl space-y-5 text-on-surface">
	<h1 class="text-2xl font-bold">Change password</h1>
	<p class="text-sm text-on-surface-variant">
		Enter your current password and confirm your new password.
	</p>
	{#if error}<p role="alert" class="rounded-lg border border-error p-3 text-error">{error}</p>{/if}
	{#if notice}<p role="status" class="rounded-lg border border-primary p-3 text-primary">
			{notice}
		</p>{/if}
	<form onsubmit={save}>
		<fieldset
			disabled={saving}
			class="space-y-5 rounded-xl border border-outline-variant bg-surface-container-low p-6"
		>
			<label class="block space-y-2"
				><span>Current password</span><input
					class="w-full rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2"
					type="password"
					name="current_password"
					required
					maxlength="72"
					autocomplete="current-password"
					bind:value={currentPassword}
				/></label
			>
			<label class="block space-y-2"
				><span>New password</span><input
					class="w-full rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2"
					type="password"
					name="new_password"
					required
					minlength="8"
					maxlength="72"
					autocomplete="new-password"
					bind:value={newPassword}
				/></label
			>
			<label class="block space-y-2"
				><span>Confirm new password</span><input
					class="w-full rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2"
					type="password"
					name="confirm_password"
					required
					minlength="8"
					maxlength="72"
					autocomplete="new-password"
					bind:value={confirmation}
				/></label
			>
			<p class="text-sm text-on-surface-variant">Use at least 8 characters.</p>
			<button
				class="rounded-lg bg-primary px-4 py-2 font-semibold text-on-primary disabled:opacity-50"
				type="submit">{saving ? 'Saving…' : 'Change password'}</button
			>
		</fieldset>
	</form>
</section>
