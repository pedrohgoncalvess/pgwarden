import { writable } from 'svelte/store';

export const selectedDatabaseId = writable<string | null>(null);
