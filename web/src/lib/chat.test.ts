import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createChat } from './chat.svelte';

function sseResponse(frames: string[]): Response {
	const stream = new ReadableStream({
		start(controller) {
			const encoder = new TextEncoder();
			for (const frame of frames) controller.enqueue(encoder.encode(frame));
			controller.close();
		}
	});
	return new Response(stream, { status: 200 });
}

const FRAMES = [
	'event: start\ndata: {"conversation_id":7,"title":"Who is Pikachu?"}\n\n',
	'event: tool\ndata: {"tool_name":"find_pokemon","args":{"name_or_id":"pikachu"},"result":{"pokemon":{"name":"Pikachu"}}}\n\n',
	'event: token\ndata: {"text":"Pikachu "}\n\n',
	'event: token\ndata: {"text":"is quick!"}\n\n',
	'event: done\ndata: {"conversation_id":7}\n\n'
];

describe('createChat', () => {
	beforeEach(() => vi.restoreAllMocks());

	it('appends the user message immediately', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(FRAMES)));
		const chat = createChat();
		await chat.send('Who is Pikachu?');
		expect(chat.messages[0].role).toBe('user');
		expect(chat.messages[0].text).toBe('Who is Pikachu?');
	});

	it('accumulates tokens and tool events onto the assistant message', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(FRAMES)));
		const chat = createChat();
		await chat.send('Who is Pikachu?');
		const assistant = chat.messages[1];
		expect(assistant.role).toBe('assistant');
		expect(assistant.text).toBe('Pikachu is quick!');
		expect(assistant.toolEvents[0].tool_name).toBe('find_pokemon');
		expect(chat.conversationId).toBe(7);
		expect(chat.busy).toBe(false);
	});

	it('shows a limit frame as the answer, not an error', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				sseResponse([
					'event: start\ndata: {"conversation_id":1,"title":"hi"}\n\n',
					'event: limit\ndata: {"message":"That\'s all the Pokémon questions for today, Drew. Come back tomorrow!"}\n\n',
					'event: done\ndata: {"conversation_id":1}\n\n'
				])
			)
		);
		const chat = createChat();
		await chat.send('one more');
		expect(chat.messages[1].text).toContain('Come back tomorrow');
		expect(chat.error).toBeNull();
	});

	it('surfaces an error frame', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				sseResponse(['event: error\ndata: {"message":"provider exploded"}\n\n'])
			)
		);
		const chat = createChat();
		await chat.send('hi');
		expect(chat.error).toContain('provider exploded');
		expect(chat.busy).toBe(false);
	});

	it('ignores an empty message', async () => {
		const fetchMock = vi.fn();
		vi.stubGlobal('fetch', fetchMock);
		const chat = createChat();
		await chat.send('   ');
		expect(fetchMock).not.toHaveBeenCalled();
		expect(chat.messages).toHaveLength(0);
	});

	it('ignores a concurrent send while busy', async () => {
		let resolveFetch: (value: Response) => void = () => {};
		const fetchMock = vi.fn().mockImplementation(
			() =>
				new Promise<Response>((resolve) => {
					resolveFetch = resolve;
				})
		);
		vi.stubGlobal('fetch', fetchMock);
		const chat = createChat();
		const first = chat.send('first question');
		const second = chat.send('second question');
		resolveFetch(sseResponse(FRAMES));
		await Promise.all([first, second]);
		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(chat.messages.filter((m) => m.role === 'user')).toHaveLength(1);
	});
});
