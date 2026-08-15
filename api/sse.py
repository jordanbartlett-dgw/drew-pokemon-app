from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
    UsageLimitExceeded,
    UsageLimits,
)
from pydantic_ai.messages import ModelMessage, TextPart
from pydantic_core import to_jsonable_python

from api.agent import PokedexDeps
from api.models import ToolEvent


def frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


CIRCLES_MESSAGE = "Whoa, that question sent me in circles! Try asking it a different way, Drew."
TOO_LONG_MESSAGE = (
    "This chat got too long for me to remember! Tap New question to start a fresh one."
)


def _limit_message(exc: UsageLimitExceeded) -> str:
    """Pick the wording that matches what actually tripped.

    `UsageLimitExceeded` (pydantic_ai.exceptions) carries no structured field for
    which limit fired -- only a message string, built in pydantic_ai/usage.py, that
    always names the limit (e.g. "Exceeded the total_tokens_limit of ..."). Matching
    on that name is the best available signal without guessing: a request_limit or
    tool_calls_limit trip means a genuine runaway tool loop, where rephrasing the
    question can help; a total_tokens_limit trip means the accumulated conversation
    history is too big to keep replaying, where rephrasing never helps and the real
    fix is starting a new conversation.
    """
    if "total_tokens_limit" in str(exc):
        return TOO_LONG_MESSAGE
    return CIRCLES_MESSAGE


@dataclass
class TurnRecorder:
    """Collects what the turn produced so the caller can persist and bill it."""

    text: str = ""
    tool_events: list[ToolEvent] = field(default_factory=list)
    new_messages: list[ModelMessage] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


async def stream_turn(
    agent: Agent[PokedexDeps],
    deps: PokedexDeps,
    prompt: str,
    history: list[ModelMessage],
    recorder: TurnRecorder,
    usage_limits: UsageLimits | None = None,
) -> AsyncIterator[str]:
    pending_args: dict[str, dict[str, Any]] = {}
    chunks: list[str] = []
    events = None
    settled = False

    try:
        async with agent.run_stream_events(
            prompt, deps=deps, message_history=history, usage_limits=usage_limits
        ) as events:
            async for event in events:
                if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                    if event.part.content:
                        chunks.append(event.part.content)
                        yield frame("token", {"text": event.part.content})

                elif isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    chunks.append(event.delta.content_delta)
                    yield frame("token", {"text": event.delta.content_delta})

                elif isinstance(event, FunctionToolCallEvent):
                    args = event.part.args
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"raw": args}
                    pending_args[event.part.tool_call_id] = args or {}

                elif isinstance(event, FunctionToolResultEvent):
                    if event.part.part_kind != "tool-return":
                        continue
                    tool_event = ToolEvent(
                        tool_name=event.part.tool_name,
                        args=pending_args.pop(event.part.tool_call_id, {}),
                        result=to_jsonable_python(event.part.content),
                    )
                    recorder.tool_events.append(tool_event)
                    yield frame("tool", tool_event.model_dump())

                elif isinstance(event, AgentRunResultEvent):
                    recorder.new_messages = event.result.new_messages()
                    recorder.text = "".join(chunks) or str(event.result.output)
                    recorder.input_tokens = event.result.usage.input_tokens
                    recorder.output_tokens = event.result.usage.output_tokens
            settled = True
    except UsageLimitExceeded as exc:
        message = _limit_message(exc)
        partial = "".join(chunks)
        # Persisted text matches what the client ends up showing: it appends this
        # same `message` to whatever tokens already streamed (see
        # web/src/lib/chat.svelte.ts's 'limit' handler), so reopening the
        # conversation shows the same thing Drew saw live instead of a truncated
        # half-answer with the limit sentence missing (Minor 9).
        recorder.text = f"{partial} {message}".strip() if partial else message
        _record_usage_so_far(recorder, events)
        settled = True
        yield frame("limit", {"message": message})
    except Exception as exc:  # noqa: BLE001 - surfaced to the browser, not swallowed
        recorder.text = "".join(chunks)
        _record_usage_so_far(recorder, events)
        settled = True
        yield frame("error", {"message": f"{type(exc).__name__}: {exc}"})
    finally:
        if not settled:
            # The caller abandoned this generator mid-turn (a `GeneratorExit` from a
            # client disconnect, or a `CancelledError` from the surrounding task) —
            # neither is caught by `except Exception` above, and both land here
            # without ever reaching `AgentRunResultEvent`. Never yield in this
            # branch: yielding during that unwind raises RuntimeError. Whatever text
            # and tool calls happened are already on `recorder`; still bill whatever
            # tokens the model already burned before the caller walked away.
            recorder.text = recorder.text or "".join(chunks)
            _record_usage_so_far(recorder, events)


def _record_usage_so_far(recorder: TurnRecorder, events: Any) -> None:
    """Bill whatever the run spent before it errored out or hit the usage cap.

    `events` (the `run_stream_events()` handle) exposes live `usage` once iteration has
    started, even after the run has failed. A tool loop that trips the limit, or a request
    that crashes mid-stream, still burned real tokens and must still count against the
    daily budget in `api/budget.py` — leaving these at zero would make runaway turns free.
    """
    if events is None:
        return
    try:
        usage = events.usage
    except Exception:  # noqa: BLE001 - usage is best-effort here, never re-raise from a handler
        return
    recorder.input_tokens = usage.input_tokens
    recorder.output_tokens = usage.output_tokens
