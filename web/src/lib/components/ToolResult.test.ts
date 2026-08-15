import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import ToolResult from './ToolResult.svelte';
import type { ToolEvent } from '../types';

const profile = {
	id: 25, name: 'Pikachu', slug: 'pikachu', generation: 1, types: ['Electric'],
	stats: { hp: 35, attack: 55, defense: 40, special_attack: 50, special_defense: 50, speed: 90, total: 320 },
	height_m: 0.4, weight_kg: 6, abilities: ['Static'],
	artwork_url: '/images/official-artwork/25.png', sprite_url: '/images/front-default/25.png',
	genus: 'Mouse Pokémon', flavor_text: null, is_legendary: false, is_mythical: false
};

function event(tool_name: ToolEvent['tool_name'], result: unknown): ToolEvent {
	return { tool_name, args: {}, result };
}

describe('ToolResult', () => {
	it('renders a card for find_pokemon', () => {
		render(ToolResult, { event: event('find_pokemon', { pokemon: profile, candidates: [] }) });
		expect(screen.getByText('Pikachu')).toBeInTheDocument();
	});

	it('renders nothing for find_pokemon with no match', () => {
		const { container } = render(ToolResult, {
			event: event('find_pokemon', { pokemon: null, candidates: ['pikachu'] })
		});
		expect(container.textContent?.trim()).toBe('');
	});

	it('renders a comparison table', () => {
		render(ToolResult, {
			event: event('compare', { pokemon: [profile], fastest: 'Pikachu', highest_total: 'Pikachu' })
		});
		expect(screen.getByText('Fastest')).toBeInTheDocument();
	});

	it('renders nothing for compare with no resolvable names', () => {
		const { container } = render(ToolResult, {
			event: event('compare', { pokemon: [], fastest: '', highest_total: '' })
		});
		expect(container.textContent?.trim()).toBe('');
	});

	it('renders a matchup with its plain-language label', () => {
		render(ToolResult, {
			event: event('type_matchup', {
				attacking_types: ['Water'],
				defending_types: ['Fire'],
				matchups: [{ attacking: 'Water', defending: 'Fire', multiplier: 2, label: 'super effective' }],
				combined_multiplier: 2
			})
		});
		expect(screen.getByText('super effective')).toBeInTheDocument();
		expect(screen.getByText('2×')).toBeInTheDocument();
	});

	it('renders an immunity (0×) matchup instead of hiding it', () => {
		render(ToolResult, {
			event: event('type_matchup', {
				attacking_types: ['Normal'],
				defending_types: ['Ghost'],
				matchups: [{ attacking: 'Normal', defending: 'Ghost', multiplier: 0, label: 'no effect' }],
				combined_multiplier: 0
			})
		});
		expect(screen.getByText('no effect')).toBeInTheDocument();
		expect(screen.getByText('0×')).toBeInTheDocument();
	});

	it('renders a not-very-effective (0.25×) matchup', () => {
		render(ToolResult, {
			event: event('type_matchup', {
				attacking_types: ['Water'],
				defending_types: ['Water', 'Grass'],
				matchups: [
					{ attacking: 'Water', defending: 'Water', multiplier: 0.5, label: 'not very effective' },
					{ attacking: 'Water', defending: 'Grass', multiplier: 0.5, label: 'not very effective' }
				],
				combined_multiplier: 0.25
			})
		});
		expect(screen.getByText('0.25×')).toBeInTheDocument();
	});

	it('renders a quadruple-effective (4×) matchup', () => {
		render(ToolResult, {
			event: event('type_matchup', {
				attacking_types: ['Rock'],
				defending_types: ['Bug', 'Flying'],
				matchups: [
					{ attacking: 'Rock', defending: 'Bug', multiplier: 2, label: 'super effective' },
					{ attacking: 'Rock', defending: 'Flying', multiplier: 2, label: 'super effective' }
				],
				combined_multiplier: 4
			})
		});
		expect(screen.getByText('4×')).toBeInTheDocument();
	});

	it('renders an evolution line', () => {
		render(ToolResult, {
			event: event('evolution_chain', {
				chain_id: 10,
				steps: [{ from_name: 'Pikachu', to_name: 'Raichu', trigger: 'use-item', min_level: null }]
			})
		});
		expect(screen.getByText('Raichu')).toBeInTheDocument();
	});

	it('renders nothing for evolution_chain when the pokemon does not evolve', () => {
		const { container } = render(ToolResult, { event: event('evolution_chain', null) });
		expect(container.textContent?.trim()).toBe('');
	});

	it('renders a single-step evolution line', () => {
		render(ToolResult, {
			event: event('evolution_chain', {
				chain_id: 1,
				steps: [{ from_name: 'Eevee', to_name: 'Vaporeon', trigger: 'use-item', min_level: null }]
			})
		});
		expect(screen.getByText('Eevee')).toBeInTheDocument();
		expect(screen.getByText('Vaporeon')).toBeInTheDocument();
	});

	it('renders a SQL result table', () => {
		render(ToolResult, {
			event: event('run_sql', {
				sql: 'SELECT name FROM v_pokemon LIMIT 200',
				columns: ['name'],
				rows: [{ name: 'Pikachu' }],
				row_count: 1,
				truncated: false
			})
		});
		expect(screen.getByText('name')).toBeInTheDocument();
		expect(screen.getByText('Pikachu')).toBeInTheDocument();
	});

	it('renders nothing for run_sql with zero rows', () => {
		const { container } = render(ToolResult, {
			event: event('run_sql', {
				sql: 'SELECT name FROM v_pokemon WHERE name = ?',
				columns: [],
				rows: [],
				row_count: 0,
				truncated: false
			})
		});
		expect(container.textContent?.trim()).toBe('');
	});

	it('shows a truncation notice for run_sql with truncated results', () => {
		render(ToolResult, {
			event: event('run_sql', {
				sql: 'SELECT name FROM v_pokemon',
				columns: ['name'],
				rows: [{ name: 'Pikachu' }],
				row_count: 200,
				truncated: true
			})
		});
		expect(screen.getByText(/Showing the first 200/)).toBeInTheDocument();
	});

	it('renders nothing for an unknown tool name', () => {
		const { container } = render(ToolResult, {
			event: { tool_name: 'unknown_tool' as ToolEvent['tool_name'], args: {}, result: { some: 'thing' } }
		});
		expect(container.textContent?.trim()).toBe('');
	});

	it('renders nothing for an absent result', () => {
		const { container } = render(ToolResult, { event: event('find_pokemon', undefined) });
		expect(container.textContent?.trim()).toBe('');
	});
});
