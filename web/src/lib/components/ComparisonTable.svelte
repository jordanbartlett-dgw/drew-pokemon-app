<script lang="ts">
	import type { Comparison } from '../types';
	import TypeBadge from './TypeBadge.svelte';

	let { comparison }: { comparison: Comparison } = $props();

	const rows = $derived([
		{ label: 'Health', key: 'hp' as const },
		{ label: 'Attack', key: 'attack' as const },
		{ label: 'Defense', key: 'defense' as const },
		{ label: 'Special Attack', key: 'special_attack' as const },
		{ label: 'Special Defense', key: 'special_defense' as const },
		{ label: 'Speed', key: 'speed' as const },
		{ label: 'Total', key: 'total' as const }
	]);

	function best(key: (typeof rows)[number]['key']): number {
		return Math.max(...comparison.pokemon.map((p) => p.stats[key]));
	}
</script>

<div class="overflow-x-auto rounded-card bg-panel p-4 shadow-md ring-1 ring-ink/5">
	<table class="w-full text-sm">
		<thead>
			<tr>
				<th class="p-2 text-left"></th>
				{#each comparison.pokemon as p (p.id)}
					<th class="p-2 text-center">
						<img src={p.sprite_url} alt={p.name} class="mx-auto h-16 w-16" />
						<div class="font-bold">{p.name}</div>
						<div class="mt-1 flex justify-center gap-1">
							{#each p.types as type (type)}<TypeBadge name={type} />{/each}
						</div>
					</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each rows as row (row.key)}
				<tr class="border-t border-ink/10">
					<td class="p-2 text-ink/70">{row.label}</td>
					{#each comparison.pokemon as p (p.id)}
						<td
							class="p-2 text-center tabular-nums"
							class:font-bold={p.stats[row.key] === best(row.key)}
							class:text-accent={p.stats[row.key] === best(row.key)}
						>
							{p.stats[row.key]}
						</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
	<p class="mt-3 text-sm text-ink/70">
		<span class="font-bold">Fastest</span>: {comparison.fastest} ·
		<span class="font-bold">Highest total</span>: {comparison.highest_total}
	</p>
</div>
