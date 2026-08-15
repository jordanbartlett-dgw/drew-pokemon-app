<script lang="ts">
	import type { MatchupReport } from '../types';
	import TypeBadge from './TypeBadge.svelte';

	let { report }: { report: MatchupReport } = $props();
</script>

<div class="rounded-card bg-panel p-4 shadow-md ring-1 ring-ink/5">
	<div class="flex flex-wrap items-center gap-2">
		{#each report.attacking_types as type (type)}<TypeBadge name={type} />{/each}
		<span class="text-ink/50">attacking</span>
		{#each report.defending_types as type (type)}<TypeBadge name={type} />{/each}
	</div>
	<p class="mt-3 text-2xl font-bold text-accent">{report.combined_multiplier}×</p>
	<ul class="mt-2 space-y-1 text-sm">
		{#each report.matchups as matchup (matchup.defending)}
			<li>
				<span class="font-medium">vs {matchup.defending}</span>
				<span class="text-ink/60">—</span>
				<span class="text-ink/60">{matchup.label}</span>
			</li>
		{/each}
	</ul>
</div>
