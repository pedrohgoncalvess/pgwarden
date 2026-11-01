import { apiFetch, authHeaders } from '$lib/auth';

export const retentionUnits = ['minutes', 'hours', 'days', 'weeks', 'months'] as const;
export type RetentionUnit = (typeof retentionUnits)[number];
export type RetentionWindow = { value: number; unit: RetentionUnit };
export type RetentionPolicy = {
	name: string;
	job_id: number | null;
	retention_interval: string | null;
	retention_seconds: number | null;
	scheduled: boolean | null;
	schedule_interval: string | null;
	next_start: string | null;
	last_run_status: string | null;
};
export type RetentionPreview = {
	name: string;
	window: RetentionWindow;
	measured_at: string;
	cutoff: string;
	current_policy: RetentionPolicy | null;
	tables?: RetentionPreview[];
	current_bytes: number;
	observed_seconds: number;
	first_sample: string | null;
	last_sample: string | null;
	bytes_per_day: number | null;
	projected_bytes: number | null;
	baseline_projected_bytes: number | null;
	policy_delta_bytes: number | null;
	footprint_delta_bytes: number | null;
	reclaimable_bytes: number;
	eligible_chunks: number;
	total_chunks: number;
	compressed_chunks: number;
	confidence: 'limited' | 'insufficient_data';
};

async function request<T>(path: string, method = 'GET', body?: RetentionWindow): Promise<T> {
	const response = await apiFetch(`/api/v1/retention${path}`, {
		method,
		headers: authHeaders(),
		cache: 'no-store',
		...(body ? { body: JSON.stringify(body) } : {})
	});
	if (!response.ok) {
		const result = await response.json().catch(() => ({}));
		throw new Error(
			typeof result.detail === 'string'
				? result.detail
				: `Retention request failed (${response.status})`
		);
	}
	return response.json();
}

export const listRetentionPolicies = () => request<RetentionPolicy[]>('');
export const previewRetention = (name: string, window: RetentionWindow) =>
	request<RetentionPreview>(`/${encodeURIComponent(name)}/preview`, 'POST', window);
export const saveRetention = (name: string, window: RetentionWindow) =>
	request<RetentionPolicy>(`/${encodeURIComponent(name)}`, 'PUT', window);
export const previewGlobalRetention = (window: RetentionWindow) =>
	request<RetentionPreview>('/global/preview', 'POST', window);
export const saveGlobalRetention = (window: RetentionWindow) =>
	request<RetentionPolicy[]>('/global', 'PUT', window);

export function initialWindow(policy: RetentionPolicy): RetentionWindow {
	const calendar = policy.retention_interval?.match(/^(?:(\d+) years?\s*)?(?:(\d+) mons?\s*)?$/);
	if (calendar && (calendar[1] || calendar[2])) {
		return { value: Number(calendar[1] ?? 0) * 12 + Number(calendar[2] ?? 0), unit: 'months' };
	}
	const seconds = Number(policy.retention_seconds);
	for (const [unit, divisor] of [
		['days', 86400],
		['hours', 3600],
		['minutes', 60]
	] as const) {
		if (seconds >= divisor && seconds % divisor === 0) return { value: seconds / divisor, unit };
	}
	return { value: 90, unit: 'days' };
}

export function formatBytes(value: number | null): string {
	if (value === null) return 'Insufficient data';
	const index =
		value === 0
			? 0
			: Math.min(4, Math.floor(Math.log(Math.max(1, Math.abs(value))) / Math.log(1024)));
	return `${(value / 1024 ** index).toLocaleString(undefined, { maximumFractionDigits: 1 })} ${['B', 'KiB', 'MiB', 'GiB', 'TiB'][index]}`;
}
