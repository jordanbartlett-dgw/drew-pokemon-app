<script lang="ts" module>
	export const STARTERS = [
		"What are Gengar's abilities?",
		'Which Water type under 10 kg is the fastest?',
		'Would Pikachu beat Onix?',
		'Build me a balanced team around Charizard.'
	];
</script>

<script lang="ts">
	let { onpick }: { onpick: (question: string) => void } = $props();
</script>

<div class="mx-auto max-w-2xl py-16 text-center">
	<h2 class="font-display text-3xl font-bold">Hey Drew, ask me anything about Pokémon.</h2>
	<p class="mt-2 text-ink/60">
		I have every Pokémon in here. Try one of these to get started.
	</p>
	<div class="mt-6 grid gap-3 sm:grid-cols-2">
		{#each STARTERS as starter (starter)}
			<button
				type="button"
				class="rounded-card bg-panel p-4 text-left text-sm shadow-sm ring-1 ring-ink/5 hover:ring-accent"
				onclick={() => onpick(starter)}
			>
				{starter}
			</button>
		{/each}
	</div>
</div>
