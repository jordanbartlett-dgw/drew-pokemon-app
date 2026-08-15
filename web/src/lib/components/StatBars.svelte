<script lang="ts">
	import type { BaseStats } from '../types';

	let { stats }: { stats: BaseStats } = $props();

	const STAT_MAX = 255;

	const rows = $derived([
		{ label: 'Health', value: stats.hp },
		{ label: 'Attack', value: stats.attack },
		{ label: 'Defense', value: stats.defense },
		{ label: 'Special Attack', value: stats.special_attack },
		{ label: 'Special Defense', value: stats.special_defense },
		{ label: 'Speed', value: stats.speed }
	]);
</script>

<div class="space-y-1.5">
	<p class="text-xs text-ink/60">
		Base stats are how strong this Pokémon is naturally, before any training.
	</p>
	{#each rows as row (row.label)}
		<div class="flex items-center gap-2">
			<span class="w-32 shrink-0 text-sm">{row.label}</span>
			<div class="h-3 flex-1 overflow-hidden rounded-full bg-ink/10">
				<div
					class="h-full rounded-full bg-accent"
					style="width: {Math.round((row.value / STAT_MAX) * 100)}%"
				></div>
			</div>
			<span class="w-10 shrink-0 text-right text-sm tabular-nums">{row.value}</span>
		</div>
	{/each}
	<div class="flex items-center gap-2 pt-1 font-bold">
		<span class="w-32 shrink-0 text-sm">Total</span>
		<span class="flex-1"></span>
		<span class="w-10 shrink-0 text-right text-sm tabular-nums">{stats.total}</span>
	</div>
</div>
