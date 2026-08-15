<script lang="ts">
	import type { SqlResult, ToolEvent } from '../types';

	let { event }: { event: ToolEvent } = $props();

	const LABELS: Record<ToolEvent['tool_name'], string> = {
		find_pokemon: 'looked it up in the Pokédex',
		type_matchup: 'checked the type chart',
		compare: 'compared them side by side',
		evolution_chain: 'traced the evolution line',
		run_sql: 'searched the whole Pokédex'
	};

	let open = $state(false);
	const sql = $derived(
		event.tool_name === 'run_sql' ? (event.result as SqlResult)?.sql : null
	);
</script>

<div class="text-xs">
	<button
		type="button"
		class="rounded-full bg-ink/5 px-3 py-1 text-ink/60 hover:bg-ink/10"
		onclick={() => (open = !open)}
	>
		{LABELS[event.tool_name] ?? event.tool_name}
	</button>
	{#if open}
		<pre class="mt-1 overflow-x-auto rounded-lg bg-ink/5 p-2 text-[11px]">{sql ??
				JSON.stringify(event.args, null, 2)}</pre>
	{/if}
</div>
