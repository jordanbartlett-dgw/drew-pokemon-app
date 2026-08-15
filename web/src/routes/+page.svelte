<script lang="ts">
	import { deleteConversation, listConversations } from '$lib/api';
	import { createChat } from '$lib/chat.svelte';
	import ChatMessage from '$lib/components/ChatMessage.svelte';
	import Composer from '$lib/components/Composer.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import type { ConversationSummary } from '$lib/types';

	const chat = createChat();
	let conversations = $state<ConversationSummary[]>([]);

	$effect(() => {
		void refresh();
	});

	async function refresh() {
		conversations = await listConversations();
	}

	async function send(text: string) {
		await chat.send(text);
		await refresh();
	}

	async function remove(id: number) {
		await deleteConversation(id);
		if (chat.conversationId === id) chat.reset();
		await refresh();
	}
</script>

<div class="flex flex-1">
	<Sidebar
		{conversations}
		activeId={chat.conversationId}
		onselect={(id) => chat.load(id)}
		onnew={() => chat.reset()}
		ondelete={remove}
	/>

	<main class="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
		<div class="flex-1 space-y-6">
			{#if chat.messages.length === 0}
				<EmptyState onpick={send} />
			{:else}
				{#each chat.messages as message, index (index)}
					<ChatMessage {message} />
				{/each}
			{/if}

			{#if chat.error}
				<p class="rounded-card bg-accent/10 p-4 text-sm text-accent">
					Something went wrong: {chat.error}
				</p>
			{/if}
		</div>

		<div class="sticky bottom-4">
			<Composer busy={chat.busy} onsend={send} />
		</div>
	</main>
</div>
