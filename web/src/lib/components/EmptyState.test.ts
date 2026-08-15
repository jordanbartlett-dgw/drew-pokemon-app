import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import EmptyState from './EmptyState.svelte';
import { STARTERS } from './EmptyState.svelte';

describe('EmptyState', () => {
	it('greets Drew by name', () => {
		render(EmptyState, { onpick: () => {} });
		expect(screen.getByText(/Hey Drew/)).toBeInTheDocument();
	});

	it('offers four starter questions', () => {
		render(EmptyState, { onpick: () => {} });
		expect(screen.getAllByRole('button')).toHaveLength(4);
	});

	it('calls onpick with the question that was clicked', async () => {
		const onpick = vi.fn();
		render(EmptyState, { onpick });
		await userEvent.click(screen.getAllByRole('button')[0]);
		expect(onpick).toHaveBeenCalledWith(STARTERS[0]);
	});
});
