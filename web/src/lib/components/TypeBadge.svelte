<script lang="ts">
	import { typeColor } from '../types';

	let { name }: { name: string } = $props();
</script>

<span
	class="rounded-full px-3 py-1 text-sm font-bold text-white shadow-sm"
	style="background-color: {typeColor(name)}"
>
	{name}
</span>
