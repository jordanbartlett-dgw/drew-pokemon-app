import { describe, expect, it } from 'vitest';
import { TYPE_COLORS, typeColor } from './types';

describe('type colors', () => {
	it('covers all eighteen Pokémon types', () => {
		expect(Object.keys(TYPE_COLORS)).toHaveLength(18);
	});

	it('looks up a colour by display name', () => {
		expect(typeColor('Electric')).toBe(TYPE_COLORS.Electric);
	});

	it('falls back for an unknown type', () => {
		expect(typeColor('Sparkle')).toBe('#9ca3af');
	});
});
