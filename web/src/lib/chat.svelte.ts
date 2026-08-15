import { loadConversation } from './api';
import { streamChat } from './sse';
import type { ToolEvent } from './types';

export interface ChatMessage {
	role: 'user' | 'assistant';
	text: string;
	toolEvents: ToolEvent[];
}

export function createChat() {
	let messages = $state<ChatMessage[]>([]);
	let busy = $state(false);
	let error = $state<string | null>(null);
	let conversationId = $state<number | null>(null);

	async function send(text: string): Promise<void> {
		const question = text.trim();
		if (!question || busy) return;

		error = null;
		busy = true;
		messages.push({ role: 'user', text: question, toolEvents: [] });

		const assistant: ChatMessage = { role: 'assistant', text: '', toolEvents: [] };
		messages.push(assistant);

		try {
			for await (const event of streamChat(question, conversationId)) {
				if (event.name === 'start') {
					conversationId = event.data.conversation_id;
				} else if (event.name === 'token') {
					assistant.text += event.data.text;
				} else if (event.name === 'tool') {
					assistant.toolEvents.push(event.data);
				} else if (event.name === 'limit') {
					// Budget or loop cap. Drew sees a sentence, not an error banner.
					assistant.text = event.data.message;
				} else if (event.name === 'error') {
					error = event.data.message;
				}
			}
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
		} finally {
			busy = false;
		}
	}

	function reset(): void {
		messages = [];
		conversationId = null;
		error = null;
	}

	async function load(id: number): Promise<void> {
		const detail = await loadConversation(id);
		if (!detail) return;
		conversationId = id;
		error = null;
		messages = detail.turns.flatMap((turn) => [
			{ role: 'user' as const, text: turn.user_text, toolEvents: [] },
			{ role: 'assistant' as const, text: turn.assistant_text, toolEvents: turn.tool_events }
		]);
	}

	return {
		get messages() {
			return messages;
		},
		get busy() {
			return busy;
		},
		get error() {
			return error;
		},
		get conversationId() {
			return conversationId;
		},
		send,
		reset,
		load
	};
}
