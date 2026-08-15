import { flushSync } from 'svelte';

/**
 * Test-only helper. Subscribes to a reactive read the way a real Svelte
 * component (`{#each messages as m}{m.text}{/each}`) would: it reads
 * `read()` inside an `$effect`, which only reruns if the tracked value was
 * mutated through the reactive proxy (not through a detached reference to
 * the same object).
 *
 * Plain `.test.ts` files can't use `$effect`/`$effect.root` directly — those
 * runes only compile in `.svelte`/`.svelte.ts` files — so this wraps them in
 * an ordinary function a `.test.ts` file can import and call.
 */
export function trackReactive<T>(read: () => T): { values: T[]; stop: () => void } {
	const values: T[] = [];
	const stop = $effect.root(() => {
		$effect(() => {
			values.push(read());
		});
	});
	flushSync();
	return { values, stop };
}
