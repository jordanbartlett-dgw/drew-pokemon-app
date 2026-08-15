import { describe, expect, it } from 'vitest';
import { parseFrames } from './sse';

describe('parseFrames', () => {
	it('parses a complete frame', () => {
		const { events, rest } = parseFrames('event: token\ndata: {"text":"hi"}\n\n');
		expect(events).toEqual([{ name: 'token', data: { text: 'hi' } }]);
		expect(rest).toBe('');
	});

	it('parses several frames at once', () => {
		const raw =
			'event: token\ndata: {"text":"a"}\n\nevent: token\ndata: {"text":"b"}\n\n';
		expect(parseFrames(raw).events).toHaveLength(2);
	});

	it('keeps a partial trailing frame in rest', () => {
		const { events, rest } = parseFrames('event: token\ndata: {"text":"a"}\n\nevent: tok');
		expect(events).toHaveLength(1);
		expect(rest).toBe('event: tok');
	});

	it('skips frames with unparseable data', () => {
		expect(parseFrames('event: token\ndata: not json\n\n').events).toEqual([]);
	});

	it('recovers a frame split across chunk boundaries mid-frame, exactly once', () => {
		const full = 'event: token\ndata: {"text":"hello"}\n\n';
		const first = full.slice(0, 15);
		const second = full.slice(15);

		const step1 = parseFrames(first);
		expect(step1.events).toHaveLength(0);

		const step2 = parseFrames(step1.rest + second);
		expect(step2.events).toEqual([{ name: 'token', data: { text: 'hello' } }]);
		expect(step2.rest).toBe('');
	});

	it('recovers a frame split inside the JSON payload', () => {
		const full = 'event: token\ndata: {"text":"hello world"}\n\n';
		const splitAt = full.indexOf('"hello world') + 5; // mid-string, inside data
		const first = full.slice(0, splitAt);
		const second = full.slice(splitAt);

		const step1 = parseFrames(first);
		expect(step1.events).toHaveLength(0);

		const step2 = parseFrames(step1.rest + second);
		expect(step2.events).toEqual([{ name: 'token', data: { text: 'hello world' } }]);
		expect(step2.rest).toBe('');
	});

	it('recovers a frame split inside the event: line', () => {
		const full = 'event: token\ndata: {"text":"hi"}\n\n';
		const first = full.slice(0, 4); // "even"
		const second = full.slice(4);

		const step1 = parseFrames(first);
		expect(step1.events).toHaveLength(0);
		expect(step1.rest).toBe('even');

		const step2 = parseFrames(step1.rest + second);
		expect(step2.events).toEqual([{ name: 'token', data: { text: 'hi' } }]);
		expect(step2.rest).toBe('');
	});

	it('does not falsely terminate a frame when the JSON payload contains an escaped \\n\\n', () => {
		const payload = JSON.stringify({ text: 'line one\n\nline two' });
		const raw = `event: token\ndata: ${payload}\n\n`;
		const { events, rest } = parseFrames(raw);
		expect(events).toEqual([{ name: 'token', data: { text: 'line one\n\nline two' } }]);
		expect(rest).toBe('');
	});

	it('parses a captured real backend frame sequence', () => {
		const raw = [
			'event: start\ndata: {"conversation_id":7,"title":"Who is Pikachu?"}\n\n',
			'event: tool\ndata: {"tool_name":"find_pokemon","args":{"name_or_id":"pikachu"},"result":{"pokemon":{"name":"Pikachu"},"candidates":[]}}\n\n',
			'event: token\ndata: {"text":"Pikachu "}\n\n',
			'event: token\ndata: {"text":"is quick!"}\n\n',
			'event: done\ndata: {"conversation_id":7}\n\n'
		].join('');
		const { events, rest } = parseFrames(raw);
		expect(events).toHaveLength(5);
		expect(events.map((e) => e.name)).toEqual(['start', 'tool', 'token', 'token', 'done']);
		expect(rest).toBe('');
	});
});
