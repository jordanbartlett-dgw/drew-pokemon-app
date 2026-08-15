<script lang="ts">
	import type { EvolutionChain } from '../types';

	let { chain }: { chain: EvolutionChain } = $props();

	function how(trigger: string | null, level: number | null): string {
		if (level) return `at level ${level}`;
		if (trigger === 'use-item') return 'with an item';
		if (trigger === 'trade') return 'by trading';
		return trigger ? trigger.replace(/-/g, ' ') : '';
	}
</script>

<div class="rounded-card bg-panel p-4 shadow-md ring-1 ring-ink/5">
	<ul class="space-y-2">
		{#each chain.steps as step (step.from_name + step.to_name)}
			<li class="flex flex-wrap items-center gap-2 text-sm">
				<span class="font-bold">{step.from_name}</span>
				<span class="text-accent">→</span>
				<span class="font-bold">{step.to_name}</span>
				<span class="text-ink/60">{how(step.trigger, step.min_level)}</span>
			</li>
		{/each}
	</ul>
</div>
