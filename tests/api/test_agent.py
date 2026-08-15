from __future__ import annotations

import pytest
from pydantic_ai import capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from api.agent import SYSTEM_PROMPT, PokedexDeps, build_agent

pytestmark = pytest.mark.anyio


def test_system_prompt_mentions_drew_and_the_views():
    assert "Drew" in SYSTEM_PROMPT
    for view in ("v_pokemon", "v_type_matchup", "v_evolution", "v_pokemon_moves"):
        assert view in SYSTEM_PROMPT


async def test_agent_registers_all_five_tools(pokedex):
    # Asserts registration, not execution: running the agent to observe tool calls
    # would drag in TestModel's dummy-argument generation, and TestModel's args are
    # deterministic across retries, so a strict-validating tool (type_matchup,
    # run_sql) that correctly rejects a bad dummy arg can never succeed on retry.
    # That's a TestModel/ModelRetry interaction, not something this test should
    # exercise. Instead, capture the registered tool names straight off the request
    # via FunctionModel and end the run immediately with no tool call at all.
    registered: set[str] = set()

    def capture_tools(messages: list[ModelMessage], info: AgentInfo):
        registered.update(t.name for t in info.function_tools)
        return ModelResponse(parts=[TextPart("ok")])

    agent = build_agent(FunctionModel(capture_tools))
    await agent.run("Tell me about Pikachu", deps=PokedexDeps(conn=pokedex))

    assert registered == {"find_pokemon", "type_matchup", "compare", "evolution_chain", "run_sql"}


async def test_run_sql_retry_loop_terminates_instead_of_looping_forever(pokedex):
    # Locks down a backstop: a model that keeps sending the same rejected SQL must
    # not be allowed to loop forever burning Drew's budget. ModelRetry plus a fixed
    # per-tool retry budget means the run raises instead of looping indefinitely.
    attempts: list[str] = []

    def call_bad_sql(messages: list[ModelMessage], info: AgentInfo):
        attempts.append("bad")
        return ModelResponse(parts=[ToolCallPart("run_sql", {"sql": "DROP TABLE pokemon"})])

    agent = build_agent(FunctionModel(call_bad_sql))
    with pytest.raises(UnexpectedModelBehavior):
        await agent.run("List them", deps=PokedexDeps(conn=pokedex))

    assert len(attempts) <= 3


async def test_find_pokemon_tool_returns_a_profile(pokedex):
    def call_find(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])
        return ModelResponse(parts=[TextPart("done")])

    agent = build_agent(FunctionModel(call_find))
    with capture_run_messages() as messages:
        await agent.run("Who is Pikachu?", deps=PokedexDeps(conn=pokedex))

    returned = [
        p for m in messages for p in m.parts if getattr(p, "part_kind", "") == "tool-return"
    ]
    assert returned[0].content.pokemon.name == "Pikachu"


async def test_bad_sql_comes_back_as_a_retry_not_a_crash(pokedex):
    attempts: list[str] = []

    def call_sql(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            attempts.append("bad")
            return ModelResponse(parts=[ToolCallPart("run_sql", {"sql": "DROP TABLE pokemon"})])
        if len(attempts) == 1:
            attempts.append("good")
            return ModelResponse(
                parts=[ToolCallPart("run_sql", {"sql": "SELECT name FROM v_pokemon"})]
            )
        return ModelResponse(parts=[TextPart("Here you go, Drew!")])

    agent = build_agent(FunctionModel(call_sql))
    result = await agent.run("List them", deps=PokedexDeps(conn=pokedex))
    assert result.output == "Here you go, Drew!"
    assert attempts == ["bad", "good"]
