export type SelectOption = { value: string; label: string; disabled?: boolean };

export function nextOption(options: SelectOption[], current: number, direction: 1 | -1): number {
	for (let step = 1; step <= options.length; step++) {
		const index =
			(((current + step * direction) % options.length) + options.length) % options.length;
		if (!options[index].disabled) return index;
	}
	return -1;
}

export function findOption(options: SelectOption[], query: string, current: number): number {
	const normalized = query.toLocaleLowerCase();
	for (let step = 1; step <= options.length; step++) {
		const index = (Math.max(-1, current) + step) % options.length;
		if (!options[index].disabled && options[index].label.toLocaleLowerCase().startsWith(normalized))
			return index;
	}
	return -1;
}
