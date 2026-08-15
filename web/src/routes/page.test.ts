import { flushSync } from 'svelte';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import Page from './+page.svelte';

const listConversations = vi
	.fn()
	.mockResolvedValue([
		{ id: 1, title: 'Who is Pikachu?', created_at: '', updated_at: '', turn_count: 1 }
	]);

vi.mock('$lib/api', () => ({
	listConversations: (...args: unknown[]) => listConversations(...args),
	deleteConversation: vi.fn(),
	loadConversation: vi.fn()
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

	it('exposes the conversation list and "New question" through a drawer trigger, for widths below the fixed sidebar breakpoint', async () => {
		render(Page);
		await Promise.resolve();
		flushSync();

		// The desktop sidebar is `hidden lg:block` — jsdom doesn't evaluate CSS
		// breakpoints, so this trigger's presence in the DOM regardless of
		// viewport is exactly what makes it reachable once real CSS hides the
		// fixed sidebar below `lg`.
		const trigger = screen.getByRole('button', { name: 'Chats' });
		expect(trigger).toBeInTheDocument();

		// Before opening, the drawer's copy of the conversation list is not
		// mounted at all (not just visually hidden) — there should be exactly
		// one "New question" button (the desktop sidebar's).
		expect(screen.getAllByRole('button', { name: 'New question' })).toHaveLength(1);

		await userEvent.click(trigger);

		expect(screen.getByRole('dialog', { name: 'Conversations' })).toBeInTheDocument();
		expect(screen.getAllByRole('button', { name: 'New question' })).toHaveLength(2);
		expect(screen.getAllByText('Who is Pikachu?').length).toBeGreaterThan(0);

		await userEvent.click(screen.getByRole('button', { name: 'Close' }));
		expect(screen.queryByRole('dialog', { name: 'Conversations' })).not.toBeInTheDocument();
	});
});
