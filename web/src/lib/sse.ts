import type { SseEvent } from './types';

export function parseFrames(buffer: string): { events: SseEvent[]; rest: string } {
	const parts = buffer.split('\n\n');
	const rest = parts.pop() ?? '';
	const events: SseEvent[] = [];

	for (const block of parts) {
		const lines = block.split('\n');
		const nameLine = lines.find((l) => l.startsWith('event: '));
		const dataLine = lines.find((l) => l.startsWith('data: '));
		if (!nameLine || !dataLine) continue;
		try {
			events.push({
				name: nameLine.slice(7).trim(),
				data: JSON.parse(dataLine.slice(6))
			} as SseEvent);
		} catch {
			// A malformed frame is dropped rather than killing the stream.
		}
	}

	return { events, rest };
}

export async function* streamChat(
	message: string,
	conversationId: number | null,
	signal?: AbortSignal
): AsyncGenerator<SseEvent> {
	const response = await fetch('/api/chat', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ message, conversation_id: conversationId }),
		signal
	});

	if (!response.ok || !response.body) {
		throw new Error(`The Pokédex is not answering (HTTP ${response.status}).`);
	}

	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	while (true) {
		const { done, value } = await reader.read();
		if (done) break;
		buffer += decoder.decode(value, { stream: true });
		const { events, rest } = parseFrames(buffer);
		buffer = rest;
		for (const event of events) yield event;
	}
}
