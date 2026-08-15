import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import PokemonCard from './PokemonCard.svelte';
import StatBars from './StatBars.svelte';
import type { BaseStats, PokemonProfile } from '../types';

const pikachu: PokemonProfile = {
	id: 25,
	name: 'Pikachu',
	slug: 'pikachu',
	generation: 1,
	types: ['Electric'],
	stats: {
		hp: 35,
		attack: 55,
		defense: 40,
		special_attack: 50,
		special_defense: 50,
		speed: 90,
		total: 320
	},
	height_m: 0.4,
	weight_kg: 6,
	abilities: ['Static'],
	artwork_url: '/images/official-artwork/25.png',
	sprite_url: '/images/front-default/25.png',
	genus: 'Mouse Pokémon',
	flavor_text: 'It raises its tail to check its surroundings.',
	is_legendary: false,
	is_mythical: false
};

describe('PokemonCard', () => {
	it('shows the name, number, and genus', () => {
		render(PokemonCard, { pokemon: pikachu });
		expect(screen.getByText('Pikachu')).toBeInTheDocument();
		expect(screen.getByText('#025')).toBeInTheDocument();
		expect(screen.getByText('Mouse Pokémon')).toBeInTheDocument();
	});

	it('shows the artwork with a useful alt text', () => {
		render(PokemonCard, { pokemon: pikachu });
		const image = screen.getByAltText('Pikachu');
		expect(image).toHaveAttribute('src', '/images/official-artwork/25.png');
	});

	it('shows every type as a badge', () => {
		render(PokemonCard, { pokemon: { ...pikachu, types: ['Fire', 'Flying'] } });
		expect(screen.getByText('Fire')).toBeInTheDocument();
		expect(screen.getByText('Flying')).toBeInTheDocument();
	});

	it('shows kid-friendly stat labels and the total', () => {
		render(PokemonCard, { pokemon: pikachu });
		expect(screen.getByText('Health')).toBeInTheDocument();
		expect(screen.getByText('Speed')).toBeInTheDocument();
		expect(screen.getByText('320')).toBeInTheDocument();
	});

	it('shows height and weight in kid units', () => {
		render(PokemonCard, { pokemon: pikachu });
		expect(screen.getByText('0.4 m')).toBeInTheDocument();
		expect(screen.getByText('6 kg')).toBeInTheDocument();
	});

	it('renders a real dual-type profile (Charizard) with the exact backend artwork URL', () => {
		const charizard: PokemonProfile = {
			id: 6,
			name: 'Charizard',
			slug: 'charizard',
			generation: 1,
			types: ['Fire', 'Flying'],
			stats: {
				hp: 78,
				attack: 84,
				defense: 78,
				special_attack: 109,
				special_defense: 85,
				speed: 100,
				total: 534
			},
			height_m: 1.7,
			weight_kg: 90.5,
			abilities: ['Blaze', 'Solar Power'],
			artwork_url: '/images/official-artwork/6.png',
			sprite_url: '/images/front-default/6.png',
			genus: 'Flame Pokémon',
			flavor_text:
				'Its wings can carry this Pokémon close to an altitude of 4,600 feet. It blows out fire at very high temperatures.',
			is_legendary: false,
			is_mythical: false
		};
		render(PokemonCard, { pokemon: charizard });
		expect(screen.getByText('Fire')).toBeInTheDocument();
		expect(screen.getByText('Flying')).toBeInTheDocument();
		expect(screen.getByAltText('Charizard')).toHaveAttribute(
			'src',
			'/images/official-artwork/6.png'
		);
	});

	it('renders without an empty box or a stray "null" when genus and flavor_text are null', () => {
		const noGenus: PokemonProfile = { ...pikachu, genus: null, flavor_text: null };
		const { container } = render(PokemonCard, { pokemon: noGenus });
		expect(container.textContent).not.toContain('null');
		// no italic flavor-text paragraph and no genus paragraph should be present
		expect(container.querySelectorAll('p').length).toBe(1); // only the StatBars explainer line
	});

	it('stat bar width is sane at the extremes (1 and 255)', () => {
		const stats: BaseStats = {
			hp: 1,
			attack: 255,
			defense: 1,
			special_attack: 255,
			special_defense: 1,
			speed: 255,
			total: 768
		};
		const { container } = render(StatBars, { stats });
		const bars = container.querySelectorAll<HTMLDivElement>('.bg-accent');
		const widths = Array.from(bars).map((bar) => bar.style.width);
		expect(widths).toContain('0%');
		expect(widths).toContain('100%');
		for (const width of widths) {
			const pct = parseFloat(width);
			expect(pct).toBeGreaterThanOrEqual(0);
			expect(pct).toBeLessThanOrEqual(100);
		}
	});
});
