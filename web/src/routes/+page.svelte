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
	let drawerOpen = $state(false);

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

	function selectConversation(id: number) {
		chat.load(id);
		drawerOpen = false;
	}

	function newConversation() {
		chat.reset();
		drawerOpen = false;
	}
</script>

<div class="flex flex-1">
	<aside class="hidden w-64 shrink-0 border-r border-ink/10 p-4 lg:block">
		<Sidebar
			{conversations}
			activeId={chat.conversationId}
			onselect={selectConversation}
			onnew={newConversation}
			ondelete={remove}
		/>
	</aside>

	<main class="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
		<div class="flex items-center justify-between lg:hidden">
			<button
				type="button"
				class="rounded-full bg-ink/5 px-4 py-2 text-sm font-bold"
				onclick={() => (drawerOpen = true)}
			>
				Chats
			</button>
		</div>

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

	{#if drawerOpen}
		<div class="fixed inset-0 z-50 flex lg:hidden" role="dialog" aria-modal="true" aria-label="Conversations">
			<button
				type="button"
				class="absolute inset-0 bg-ink/40"
				aria-label="Close conversations"
				onclick={() => (drawerOpen = false)}
			></button>
			<div class="relative z-10 flex h-full w-72 flex-col bg-panel p-4 shadow-xl">
				<button
					type="button"
					class="mb-4 self-end rounded-full px-3 py-2 text-sm font-bold text-ink/60 hover:bg-ink/5"
					onclick={() => (drawerOpen = false)}
				>
					Close
				</button>
				<Sidebar
					{conversations}
					activeId={chat.conversationId}
					onselect={selectConversation}
					onnew={newConversation}
					ondelete={remove}
				/>
			</div>
		</div>
	{/if}
</div>
