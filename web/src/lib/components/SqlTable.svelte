<script lang="ts">
	import type { SqlResult } from '../types';

	let { result }: { result: SqlResult } = $props();
</script>

<div class="overflow-x-auto rounded-card bg-panel p-4 shadow-md ring-1 ring-ink/5">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-ink/10">
				{#each result.columns as column (column)}
					<th class="p-2 text-left font-bold">{column}</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each result.rows as row, index (index)}
				<tr class="border-b border-ink/5">
					{#each result.columns as column (column)}
						<td class="p-2">{row[column]}</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
	{#if result.truncated}
		<p class="mt-2 text-xs text-ink/60">Showing the first {result.row_count} results.</p>
	{/if}
</div>
