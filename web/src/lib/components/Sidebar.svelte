<script lang="ts">
	import type { ConversationSummary } from '../types';

	let {
		conversations,
		activeId,
		onselect,
		onnew,
		ondelete
	}: {
		conversations: ConversationSummary[];
		activeId: number | null;
		onselect: (id: number) => void;
		onnew: () => void;
		ondelete: (id: number) => void;
	} = $props();

	// A bare "x" is one tap away from destroying a conversation Drew can't get
	// back. window.confirm gives him a big, native, unmissable stop before
	// that happens without any extra markup or state to keep track of.
	function confirmDelete(conversation: ConversationSummary) {
		if (confirm(`Delete "${conversation.title}"? This can't be undone.`)) {
			ondelete(conversation.id);
		}
	}
</script>

<button
	type="button"
	class="w-full rounded-full bg-accent px-4 py-2 text-sm font-bold text-white"
	onclick={onnew}
>
	New question
</button>
<ul class="mt-4 space-y-1">
	{#each conversations as conversation (conversation.id)}
		<li class="flex items-center gap-1">
			<button
				type="button"
				class="flex-1 truncate rounded-lg px-3 py-2 text-left text-sm hover:bg-ink/5 {conversation.id ===
				activeId
					? 'bg-ink/5'
					: ''}"
				onclick={() => onselect(conversation.id)}
			>
				{conversation.title}
			</button>
			<button
				type="button"
				aria-label="Delete {conversation.title}"
				class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-lg text-ink/40 hover:bg-ink/5 hover:text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
				onclick={() => confirmDelete(conversation)}
			>
				×
			</button>
		</li>
	{/each}
</ul>
