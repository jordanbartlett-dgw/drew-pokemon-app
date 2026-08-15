<script lang="ts">
	import type { PokemonProfile } from '../types';
	import StatBars from './StatBars.svelte';
	import TypeBadge from './TypeBadge.svelte';

	let { pokemon }: { pokemon: PokemonProfile } = $props();

	const number = $derived(`#${String(pokemon.id).padStart(3, '0')}`);
</script>

<article class="rounded-card bg-panel p-5 shadow-md ring-1 ring-ink/5">
	<div class="flex flex-col gap-5 sm:flex-row">
		<img
			src={pokemon.artwork_url}
			alt={pokemon.name}
			loading="lazy"
			class="mx-auto h-56 w-56 shrink-0 object-contain"
		/>
		<div class="flex-1 space-y-3">
			<header class="space-y-1">
				<div class="flex items-baseline gap-2">
					<h3 class="font-display text-3xl font-bold">{pokemon.name}</h3>
					<span class="text-lg text-ink/50 tabular-nums">{number}</span>
				</div>
				{#if pokemon.genus}
					<p class="text-sm text-ink/60">{pokemon.genus}</p>
				{/if}
			</header>

			<div class="flex flex-wrap gap-2">
				{#each pokemon.types as type (type)}
					<TypeBadge name={type} />
				{/each}
			</div>

			<dl class="flex gap-6 text-sm">
				<div><dt class="text-ink/60">Height</dt><dd>{pokemon.height_m} m</dd></div>
				<div><dt class="text-ink/60">Weight</dt><dd>{pokemon.weight_kg} kg</dd></div>
				<div>
					<dt class="text-ink/60">Abilities</dt>
					<dd>{pokemon.abilities.join(', ') || '—'}</dd>
				</div>
			</dl>

			<StatBars stats={pokemon.stats} />

			{#if pokemon.flavor_text}
				<p class="border-l-4 border-accent/40 pl-3 text-sm italic text-ink/70">
					{pokemon.flavor_text}
				</p>
			{/if}
		</div>
	</div>
</article>
