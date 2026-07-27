export type NotificationLevel = 'critical' | 'warning' | 'info';

export type NotificationItem = {
	id: number;
	message: string;
	hidden: boolean;
	params: Record<string, unknown>;
	created_at: string;
};

export type NotificationListResponse = {
	items: NotificationItem[];
	total: number;
	visible_count: number;
	hidden_count: number;
	level_counts: Record<NotificationLevel, number>;
};

function authHeaders(): Record<string, string> {
	const token = localStorage.getItem('token');
	return {
		'Content-Type': 'application/json',
		...(token ? { Authorization: `Bearer ${token}` } : {})
	};
}

export async function listNotifications(options: {
	hidden?: boolean;
	level?: NotificationLevel;
	limit?: number;
	offset?: number;
}): Promise<NotificationListResponse> {
	const url = new URL('/api/v1/notifications/', window.location.origin);
	url.searchParams.set('hidden', String(options.hidden ?? false));
	url.searchParams.set('limit', String(options.limit ?? 100));
	url.searchParams.set('offset', String(options.offset ?? 0));
	if (options.level) url.searchParams.set('level', options.level);

	const response = await fetch(url, { headers: authHeaders() });
	if (!response.ok) {
		throw new Error(`Failed to list notifications: ${response.status}`);
	}
	return response.json();
}

export async function setNotificationHidden(
	notificationId: number,
	hidden: boolean
): Promise<NotificationItem> {
	const response = await fetch(`/api/v1/notifications/${notificationId}`, {
		method: 'PATCH',
		headers: authHeaders(),
		body: JSON.stringify({ hidden })
	});
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.detail || `Failed to update notification: ${response.status}`);
	}
	return response.json();
}
