from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field


class BaseStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int

    @computed_field
    @property
    def total(self) -> int:
        return (
            self.hp
            + self.attack
            + self.defense
            + self.special_attack
            + self.special_defense
            + self.speed
        )


class PokemonProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    slug: str
    generation: int
    types: list[str]
    stats: BaseStats
    height_m: float
    weight_kg: float
    abilities: list[str]
    artwork_url: str
    sprite_url: str
    genus: str | None = None
    flavor_text: str | None = None
    is_legendary: bool = False
    is_mythical: bool = False


class FindPokemonResult(BaseModel):
    """Either a match, or the closest names so the model can ask Drew which he meant."""

    model_config = ConfigDict(frozen=True)

    pokemon: PokemonProfile | None = None
    candidates: list[str] = []


class TypeMatchup(BaseModel):
    model_config = ConfigDict(frozen=True)

    attacking: str
    defending: str
    multiplier: float

    @computed_field
    @property
    def label(self) -> str:
        if self.multiplier == 0:
            return "no effect"
        if self.multiplier > 1:
            return "super effective"
        if self.multiplier < 1:
            return "not very effective"
        return "normal damage"


class MatchupReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    attacking_types: list[str]
    defending_types: list[str]
    matchups: list[TypeMatchup]
    combined_multiplier: float


class Comparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    pokemon: list[PokemonProfile]
    fastest: str
    highest_total: str


class EvolutionStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_name: str
    to_name: str
    trigger: str | None = None
    min_level: int | None = None


class EvolutionChain(BaseModel):
    model_config = ConfigDict(frozen=True)

    chain_id: int
    steps: list[EvolutionStep]


class SqlResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool


class ToolEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    args: dict[str, Any] = {}
    result: Any = None


class StoredTurn(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    user_text: str
    assistant_text: str
    tool_events: list[ToolEvent] = []
    created_at: str


class ConversationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    created_at: str
    updated_at: str
    turn_count: int
