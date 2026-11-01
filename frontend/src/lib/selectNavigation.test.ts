import { describe, expect, it } from 'vitest';
import { findOption, nextOption } from './selectNavigation';

const options = [
	{ value: '', label: 'Select', disabled: true },
	{ value: 'a', label: 'Alpha' },
	{ value: 'b', label: 'Beta', disabled: true },
	{ value: 'c', label: 'Charlie' }
];

describe('select keyboard navigation', () => {
	it('wraps in both directions and skips disabled options', () => {
		expect(nextOption(options, 1, 1)).toBe(3);
		expect(nextOption(options, 3, 1)).toBe(1);
		expect(nextOption(options, 1, -1)).toBe(3);
	});
	it('handles empty and fully disabled lists', () => {
		expect(nextOption([], -1, 1)).toBe(-1);
		expect(
			nextOption(
				options.map((option) => ({ ...option, disabled: true })),
				0,
				1
			)
		).toBe(-1);
	});
	it('finds typed labels case-insensitively and ignores disabled matches', () => {
		expect(findOption(options, 'CH', 1)).toBe(3);
		expect(findOption(options, 'be', 1)).toBe(-1);
		expect(findOption([], 'a', -1)).toBe(-1);
	});
});
