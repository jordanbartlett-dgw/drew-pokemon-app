<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>
<div class="flex min-h-screen flex-col">
	<header class="border-b border-ink/10 px-6 py-4">
		<h1 class="font-display text-2xl font-bold">Drew's Pokémon App</h1>
	</header>
	{@render children()}
</div>
