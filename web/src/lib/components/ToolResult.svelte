<script lang="ts">
	import type {
		Comparison,
		EvolutionChain,
		FindPokemonResult,
		MatchupReport,
		SqlResult,
		ToolEvent
	} from '../types';
	import ComparisonTable from './ComparisonTable.svelte';
	import EvolutionLine from './EvolutionLine.svelte';
	import PokemonCard from './PokemonCard.svelte';
	import SqlTable from './SqlTable.svelte';
	import TypeChart from './TypeChart.svelte';

	let { event }: { event: ToolEvent } = $props();
</script>

{#if event.tool_name === 'find_pokemon' && (event.result as FindPokemonResult)?.pokemon}
	<PokemonCard pokemon={(event.result as FindPokemonResult).pokemon!} />
{:else if event.tool_name === 'compare' && (event.result as Comparison)?.pokemon?.length}
	<ComparisonTable comparison={event.result as Comparison} />
{:else if event.tool_name === 'type_matchup' && event.result}
	<TypeChart report={event.result as MatchupReport} />
{:else if event.tool_name === 'evolution_chain' && (event.result as EvolutionChain)?.steps?.length}
	<EvolutionLine chain={event.result as EvolutionChain} />
{:else if event.tool_name === 'run_sql' && (event.result as SqlResult)?.row_count}
	<SqlTable result={event.result as SqlResult} />
{/if}
