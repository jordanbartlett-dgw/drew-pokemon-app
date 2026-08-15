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
	// Plain (non-reactive) handle to the in-flight request so reset() can cancel it.
	let activeController: AbortController | null = null;

	async function send(text: string): Promise<void> {
		const question = text.trim();
		if (!question || busy) return;

		error = null;
		busy = true;
		messages.push({ role: 'user', text: question, toolEvents: [] });
		messages.push({ role: 'assistant', text: '', toolEvents: [] });
		// `$state` arrays deep-proxy their contents: `messages.push(...)` wraps the
		// pushed object in a NEW proxy. Mutating the object literal we just pushed
		// (a detached reference) bypasses that proxy's `set` trap entirely, so no
		// reactive consumer is ever notified. Re-reading the element back out of the
		// array gives us the live, proxy-wrapped element instead.
		const assistantIndex = messages.length - 1;

		const controller = new AbortController();
		activeController = controller;

		try {
			for await (const event of streamChat(question, conversationId, controller.signal)) {
				if (controller.signal.aborted) break;
				// reset() may have replaced `messages` with a fresh array mid-stream;
				// a late frame from the abandoned request must not touch it.
				const live = messages[assistantIndex];
				if (!live) break;

				if (event.name === 'start') {
					conversationId = event.data.conversation_id;
				} else if (event.name === 'token') {
					live.text += event.data.text;
				} else if (event.name === 'tool') {
					live.toolEvents.push(event.data);
				} else if (event.name === 'limit') {
					// Budget or loop cap. Drew sees a sentence, not an error banner. Append
					// rather than replace so a partial answer that already streamed stays
					// visible -- api/sse.py persists the same partial-plus-message text, so
					// reopening the conversation later shows exactly what was live here.
					live.text = live.text ? `${live.text} ${event.data.message}` : event.data.message;
				} else if (event.name === 'error') {
					error = event.data.message;
				}
			}
		} catch (cause) {
			if (!controller.signal.aborted) {
				error = cause instanceof Error ? cause.message : String(cause);
			}
		} finally {
			// If reset() already fired, it owns `busy`/`activeController` — don't
			// clobber a newer send's state with this abandoned request's cleanup.
			if (activeController === controller) {
				busy = false;
				activeController = null;
			}
		}
	}

	function reset(): void {
		activeController?.abort();
		activeController = null;
		messages = [];
		conversationId = null;
		error = null;
		busy = false;
	}

	async function load(id: number): Promise<void> {
		// A conversation from the sidebar can be opened while a previous send()
		// is still streaming. That request's late frames must not land on the
		// conversation we're about to load.
		activeController?.abort();
		activeController = null;
		busy = false;

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
