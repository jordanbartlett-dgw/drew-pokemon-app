import type { ConversationSummary, StoredTurn } from './types';

export async function listConversations(): Promise<ConversationSummary[]> {
	const response = await fetch('/api/conversations');
	if (!response.ok) return [];
	return response.json();
}

export async function loadConversation(
	id: number
): Promise<{ conversation: ConversationSummary; turns: StoredTurn[] } | null> {
	const response = await fetch(`/api/conversations/${id}`);
	if (!response.ok) return null;
	return response.json();
}

export async function deleteConversation(id: number): Promise<void> {
	await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
}
