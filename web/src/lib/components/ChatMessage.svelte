<script lang="ts">
	import type { ChatMessage } from '../chat.svelte';
	import ToolChip from './ToolChip.svelte';
	import ToolResult from './ToolResult.svelte';

	let { message }: { message: ChatMessage } = $props();
</script>

{#if message.role === 'user'}
	<div class="flex justify-end">
		<p class="max-w-[80%] rounded-card bg-accent px-4 py-2 text-white">{message.text}</p>
	</div>
{:else}
	<div class="space-y-3">
		{#if message.toolEvents.length}
			<div class="flex flex-wrap gap-2">
				{#each message.toolEvents as event, index (index)}
					<ToolChip {event} />
				{/each}
			</div>
		{/if}
		{#if message.text}
			<p class="whitespace-pre-wrap leading-relaxed">{message.text}</p>
		{/if}
		{#each message.toolEvents as event, index (index)}
			<ToolResult {event} />
		{/each}
	</div>
{/if}
