export interface BaseStats {
	hp: number;
	attack: number;
	defense: number;
	special_attack: number;
	special_defense: number;
	speed: number;
	total: number;
}

export interface PokemonProfile {
	id: number;
	name: string;
	slug: string;
	generation: number;
	types: string[];
	stats: BaseStats;
	height_m: number;
	weight_kg: number;
	abilities: string[];
	artwork_url: string;
	sprite_url: string;
	genus: string | null;
	flavor_text: string | null;
	is_legendary: boolean;
	is_mythical: boolean;
}

export interface FindPokemonResult {
	pokemon: PokemonProfile | null;
	candidates: string[];
}

export interface TypeMatchup {
	attacking: string;
	defending: string;
	multiplier: number;
	label: string;
}

export interface MatchupReport {
	attacking_types: string[];
	defending_types: string[];
	matchups: TypeMatchup[];
	combined_multiplier: number;
}

export interface Comparison {
	pokemon: PokemonProfile[];
	fastest: string;
	highest_total: string;
}

export interface EvolutionStep {
	from_name: string;
	to_name: string;
	trigger: string | null;
	min_level: number | null;
}

export interface EvolutionChain {
	chain_id: number;
	steps: EvolutionStep[];
}

export interface SqlResult {
	sql: string;
	columns: string[];
	rows: Record<string, unknown>[];
	row_count: number;
	truncated: boolean;
}

export type ToolName =
	| 'find_pokemon'
	| 'type_matchup'
	| 'compare'
	| 'evolution_chain'
	| 'run_sql';

export interface ToolEvent {
	tool_name: ToolName;
	args: Record<string, unknown>;
	result: unknown;
}

export interface StoredTurn {
	id: number;
	user_text: string;
	assistant_text: string;
	tool_events: ToolEvent[];
	created_at: string;
}

export interface ConversationSummary {
	id: number;
	title: string;
	created_at: string;
	updated_at: string;
	turn_count: number;
}

export type SseEvent =
	| { name: 'start'; data: { conversation_id: number; title: string } }
	| { name: 'token'; data: { text: string } }
	| { name: 'tool'; data: ToolEvent }
	| { name: 'limit'; data: { message: string } }
	| { name: 'done'; data: { conversation_id: number } }
	| { name: 'error'; data: { message: string } };

export const TYPE_COLORS: Record<string, string> = {
	Normal: '#9fa19f',
	Fighting: '#ff8000',
	Flying: '#81b9ef',
	Poison: '#9141cb',
	Ground: '#915121',
	Rock: '#afa981',
	Bug: '#91a119',
	Ghost: '#704170',
	Steel: '#60a1b8',
	Fire: '#e62829',
	Water: '#2980ef',
	Grass: '#3fa129',
	Electric: '#fac000',
	Psychic: '#ef4179',
	Ice: '#3dcef3',
	Dragon: '#5060e1',
	Dark: '#624d4e',
	Fairy: '#ef70ef'
};

export function typeColor(name: string): string {
	return TYPE_COLORS[name] ?? '#9ca3af';
}
