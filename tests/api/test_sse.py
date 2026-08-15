from __future__ import annotations

import json

import pytest
from pydantic_ai import UsageLimits
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from api.agent import PokedexDeps, build_agent
from api.sse import CIRCLES_MESSAGE, TOO_LONG_MESSAGE, TurnRecorder, frame, stream_turn

pytestmark = pytest.mark.anyio

# `stream_turn` drives `agent.run_stream_events`, which always takes pydantic-ai's
# streaming request path. On 2.31.0, `FunctionModel.request_stream` hard-requires a
# `stream_function` (see `FunctionModel.request_stream`, function.py:198) — a plain
# `function=` script, sufficient for `agent.run()`, is not enough here. Each script
# below therefore ships a matching `stream_*` twin that yields the same tool call or
# text as a single delta chunk, mirroring the non-streaming version exactly.


def test_frame_format():
    assert frame("token", {"text": "hi"}) == 'event: token\ndata: {"text": "hi"}\n\n'


def _parse(frames: list[str]) -> list[tuple[str, dict]]:
    parsed = []
    for raw in frames:
        lines = raw.strip().split("\n")
        parsed.append(
            (lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: ")))
        )
    return parsed


async def test_streams_tokens_and_tool_results(pokedex):
    def script(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])
        return ModelResponse(parts=[TextPart("Pikachu is an Electric mouse!")])

    async def stream_script(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="find_pokemon",
                    json_args=json.dumps({"name_or_id": "pikachu"}),
                    tool_call_id="call_1",
                )
            }
        else:
            yield "Pikachu is an Electric mouse!"

    recorder = TurnRecorder()
    agent = build_agent(FunctionModel(script, stream_function=stream_script))
    frames = [
        f
        async for f in stream_turn(
            agent, PokedexDeps(conn=pokedex), "Who is Pikachu?", [], recorder
        )
    ]
    events = _parse(frames)

    tool_events = [d for name, d in events if name == "tool"]
    assert tool_events[0]["tool_name"] == "find_pokemon"
    assert tool_events[0]["args"] == {"name_or_id": "pikachu"}
    assert tool_events[0]["result"]["pokemon"]["name"] == "Pikachu"

    text = "".join(d["text"] for name, d in events if name == "token")
    assert text == "Pikachu is an Electric mouse!"


async def test_recorder_captures_turn_state(pokedex):
    def script(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])
        return ModelResponse(parts=[TextPart("All done, Drew!")])

    async def stream_script(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="find_pokemon",
                    json_args=json.dumps({"name_or_id": "pikachu"}),
                    tool_call_id="call_1",
                )
            }
        else:
            yield "All done, Drew!"

    recorder = TurnRecorder()
    agent = build_agent(FunctionModel(script, stream_function=stream_script))
    async for _ in stream_turn(agent, PokedexDeps(conn=pokedex), "Who?", [], recorder):
        pass

    assert recorder.text == "All done, Drew!"
    assert recorder.tool_events[0].tool_name == "find_pokemon"
    assert len(recorder.new_messages) >= 2


async def test_usage_limit_emits_a_limit_frame_not_an_error(pokedex):
    def loop(messages: list[ModelMessage], info: AgentInfo):
        return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])

    async def stream_loop(messages: list[ModelMessage], info: AgentInfo):
        yield {
            0: DeltaToolCall(
                name="find_pokemon",
                json_args=json.dumps({"name_or_id": "pikachu"}),
                tool_call_id="call_1",
            )
        }

    recorder = TurnRecorder()
    agent = build_agent(FunctionModel(loop, stream_function=stream_loop))
    frames = [
        f
        async for f in stream_turn(
            agent,
            PokedexDeps(conn=pokedex),
            "loop forever",
            [],
            recorder,
            UsageLimits(request_limit=3),
        )
    ]
    names = [name for name, _ in _parse(frames)]
    assert names[-1] == "limit"
    # request_limit is a runaway-tool-loop cap, where rephrasing genuinely can help,
    # so this must use CIRCLES_MESSAGE, not the total_tokens_limit wording.
    assert _parse(frames)[-1][1]["message"] == CIRCLES_MESSAGE
    # Tokens burned before the limit tripped must still be billed against the daily
    # cap in api/budget.py — a runaway loop is the single most expensive turn the app
    # can produce, and it must not be the one turn that bills nothing.
    assert recorder.input_tokens > 0
    assert recorder.output_tokens > 0


async def test_total_tokens_limit_uses_the_conversation_too_long_message(pokedex):
    """Critical 1 part 4: total_tokens_limit means the accumulated history is too
    big to keep replaying -- rephrasing the question can never help, unlike a
    request_limit/tool_calls_limit trip, so it needs different wording."""

    def loop(messages: list[ModelMessage], info: AgentInfo):
        return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])

    async def stream_loop(messages: list[ModelMessage], info: AgentInfo):
        yield {
            0: DeltaToolCall(
                name="find_pokemon",
                json_args=json.dumps({"name_or_id": "pikachu"}),
                tool_call_id="call_1",
            )
        }

    recorder = TurnRecorder()
    agent = build_agent(FunctionModel(loop, stream_function=stream_loop))
    frames = [
        f
        async for f in stream_turn(
            agent,
            PokedexDeps(conn=pokedex),
            "a very long conversation",
            [],
            recorder,
            UsageLimits(total_tokens_limit=1),
        )
    ]
    assert _parse(frames)[-1][1]["message"] == TOO_LONG_MESSAGE
    assert recorder.text == TOO_LONG_MESSAGE


async def test_model_failure_emits_an_error_frame(pokedex):
    # The crash happens on the *second* model call, after a real tool call already
    # burned tokens, so a token assertion here actually exercises the "tokens spent
    # before the crash are still recorded" behavior rather than trivially passing on
    # a turn that never spent anything.
    def boom(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])
        raise RuntimeError("provider exploded")

    async def stream_boom(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="find_pokemon",
                    json_args=json.dumps({"name_or_id": "pikachu"}),
                    tool_call_id="call_1",
                )
            }
        else:
            raise RuntimeError("provider exploded")
            yield ""  # pragma: no cover - unreachable, makes this an async generator

    recorder = TurnRecorder()
    agent = build_agent(FunctionModel(boom, stream_function=stream_boom))
    frames = [f async for f in stream_turn(agent, PokedexDeps(conn=pokedex), "Who?", [], recorder)]
    names = [name for name, _ in _parse(frames)]
    assert names[-1] == "error"
    assert recorder.input_tokens > 0
    assert recorder.output_tokens > 0
