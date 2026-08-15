import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import Sidebar from './Sidebar.svelte';
import type { ConversationSummary } from '../types';

const conversations: ConversationSummary[] = [
	{ id: 1, title: 'Who is Pikachu?', created_at: '', updated_at: '', turn_count: 1 }
];

describe('Sidebar', () => {
	it('shows the delete control without any hover interaction (touch has no hover)', () => {
		render(Sidebar, {
			conversations,
			activeId: null,
			onselect: () => {},
			onnew: () => {},
			ondelete: () => {}
		});

		const deleteButton = screen.getByLabelText('Delete Who is Pikachu?');
		expect(deleteButton).toBeInTheDocument();
		// The old bug was `opacity-0 group-hover:opacity-100` — invisible until a
		// hover event that touch devices never send. It must never be opacity-0.
		expect(deleteButton.className).not.toContain('opacity-0');
		// At least a 44x44 tap target so a kid's finger can hit it.
		expect(deleteButton.className).toContain('h-11');
		expect(deleteButton.className).toContain('w-11');
	});

	it('asks for confirmation before deleting, and only deletes if confirmed', async () => {
		const ondelete = vi.fn();
		vi.stubGlobal('confirm', vi.fn().mockReturnValue(false));
		render(Sidebar, {
			conversations,
			activeId: null,
			onselect: () => {},
			onnew: () => {},
			ondelete
		});

		await userEvent.click(screen.getByLabelText('Delete Who is Pikachu?'));
		expect(ondelete).not.toHaveBeenCalled();

		vi.stubGlobal('confirm', vi.fn().mockReturnValue(true));
		await userEvent.click(screen.getByLabelText('Delete Who is Pikachu?'));
		expect(ondelete).toHaveBeenCalledWith(1);

		vi.unstubAllGlobals();
	});

	it('calls onselect when a conversation is tapped', async () => {
		const onselect = vi.fn();
		render(Sidebar, {
			conversations,
			activeId: null,
			onselect,
			onnew: () => {},
			ondelete: () => {}
		});

		await userEvent.click(screen.getByText('Who is Pikachu?'));
		expect(onselect).toHaveBeenCalledWith(1);
	});
});
