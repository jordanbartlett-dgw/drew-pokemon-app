<script lang="ts">
	let {
		busy,
		onsend
	}: { busy: boolean; onsend: (text: string) => void } = $props();

	let text = $state('');

	function submit(submitEvent: SubmitEvent) {
		submitEvent.preventDefault();
		if (!text.trim() || busy) return;
		onsend(text);
		text = '';
	}
</script>

<form class="flex gap-2" onsubmit={submit}>
	<input
		bind:value={text}
		placeholder="Ask about any Pokémon…"
		aria-label="Ask about any Pokémon"
		class="flex-1 rounded-full bg-panel px-5 py-3 shadow-sm ring-1 ring-ink/10 outline-none focus:ring-accent"
	/>
	<button
		type="submit"
		disabled={busy || !text.trim()}
		class="rounded-full bg-accent px-6 py-3 font-bold text-white disabled:opacity-40"
	>
		{busy ? 'Thinking…' : 'Ask'}
	</button>
</form>
