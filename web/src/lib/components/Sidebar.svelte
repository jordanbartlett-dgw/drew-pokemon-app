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
</script>

<aside class="hidden w-64 shrink-0 border-r border-ink/10 p-4 lg:block">
	<button
		type="button"
		class="w-full rounded-full bg-accent px-4 py-2 text-sm font-bold text-white"
		onclick={onnew}
	>
		New question
	</button>
	<ul class="mt-4 space-y-1">
		{#each conversations as conversation (conversation.id)}
			<li class="group flex items-center gap-1">
				<button
					type="button"
					class="flex-1 truncate rounded-lg px-3 py-2 text-left text-sm hover:bg-ink/5"
					class:bg-ink-5={conversation.id === activeId}
					onclick={() => onselect(conversation.id)}
				>
					{conversation.title}
				</button>
				<button
					type="button"
					aria-label="Delete {conversation.title}"
					class="px-2 text-ink/30 opacity-0 group-hover:opacity-100 hover:text-accent"
					onclick={() => ondelete(conversation.id)}
				>
					×
				</button>
			</li>
		{/each}
	</ul>
</aside>
