import { describe, expect, it } from 'vitest';
import { DAY_MS, recentRange } from './timeRange';

describe('initial history range', () => {
	it.each(['2026-10-31T15:23:00Z', '2027-01-01T12:00:00Z', '2026-03-01T12:00:00Z'])(
		'opens the last 24 hours ending now, including across month/year boundaries (%s)',
		(instant) => {
			const now = new Date(instant);
			const range = recentRange(undefined, now);
			expect(new Date(range.end).getTime()).toBe(now.getTime());
			expect(new Date(range.start).getTime()).toBe(now.getTime() - DAY_MS);
		}
	);
	it('still allows an explicitly requested longer period', () => {
		const range = recentRange(7, new Date('2026-10-31T15:23:00Z'));
		expect(new Date(range.end).getTime() - new Date(range.start).getTime()).toBe(7 * DAY_MS);
	});
});
