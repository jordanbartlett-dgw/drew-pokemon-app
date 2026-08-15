import { flushSync } from 'svelte';
import { render } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import Page from './+page.svelte';

const listConversations = vi.fn().mockResolvedValue([]);

vi.mock('$lib/api', () => ({
	listConversations: (...args: unknown[]) => listConversations(...args),
	deleteConversation: vi.fn()
}));

describe('+page.svelte', () => {
	it('does not loop: reassigning `conversations` inside refresh() does not retrigger the effect', async () => {
		render(Page);

		// Let the effect's `void refresh()` microtask (the `await listConversations()`
		// inside it) resolve and settle. If the effect read `conversations` — the
		// value it later reassigns — Svelte would treat that as a dependency and
		// rerun the effect every time `refresh()` completes, calling the API
		// forever. Flushing a few times gives any such loop room to show up.
		await Promise.resolve();
		flushSync();
		await Promise.resolve();
		flushSync();
		await Promise.resolve();
		flushSync();

		expect(listConversations).toHaveBeenCalledTimes(1);
	});
});
