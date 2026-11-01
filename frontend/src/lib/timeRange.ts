export const DEFAULT_ANALYTICS_PRESET = '1d' as const;
export const DAY_MS = 24 * 60 * 60 * 1000;

export function toLocalDateTime(value: Date): string {
	return new Date(value.getTime() - value.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export function recentRange(days = 1, now = new Date()) {
	return {
		start: toLocalDateTime(new Date(now.getTime() - days * DAY_MS)),
		end: toLocalDateTime(now)
	};
}
