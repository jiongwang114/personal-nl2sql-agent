"""
API routes for Chat endpoints.

All business logic (session queries, history retrieval) is delegated to
ChatService via DataEngineerService. Routes are thin wrappers that handle HTTP
concerns only.

Streaming endpoints use the project-scoped ChatTaskManager (via
DataEngineerService.task_manager) to run the agentic loop in a background
asyncio.Task so that client disconnects do not cancel the computation.
"""

import json
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import StreamingResponse

from dataengineer.api.constants import BUILTIN_SUBAGENTS
from dataengineer.api.deps import AppContextDep, ServiceDep
from dataengineer.api.models.base_models import Result
from dataengineer.api.models.chat_models import (
    ResumeChatInput,
    StopChatInput,
    ToolResultData,
    ToolResultInput,
)
from dataengineer.api.models.cli_models import (
    ChatHistoryData,
    ChatModelData,
    ChatSessionData,
    CompactSessionData,
    CompactSessionInput,
    FeedbackChatInput,
    SSEErrorData,
    SSEEvent,
    StreamChatInput,
    UserInteractionInput,
)
from dataengineer.utils.feedback_prompt import build_reaction_feedback_prompt
from dataengineer.utils.loggings import get_logger

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
logger = get_logger(__name__)


# Additional builtin subagents accepted by ``stream_chat`` beyond the canonical
# ``BUILTIN_SUBAGENTS`` set — these are wired directly in
# ``ChatTaskManager._create_node`` but are not listed as user-creatable agents
# in ``datus.api.constants``. Keep this list in sync with the dispatch branches
# in :meth:`ChatTaskManager._create_node`.
_EXTRA_BUILTIN_SUBAGENTS = {"feedback"}


def _is_valid_subagent_id(svc, subagent_id: str) -> bool:
    """Return True if *subagent_id* resolves to a builtin or custom sub-agent."""
    if subagent_id in BUILTIN_SUBAGENTS or subagent_id in _EXTRA_BUILTIN_SUBAGENTS:
        return True
    agentic_nodes = getattr(svc.agent_config, "agentic_nodes", None) or {}
    if subagent_id in agentic_nodes:
        return True
    # Custom sub-agents may be keyed by sanitized node_name with the original
    # UUID id stored under "id" — match either form.
    for entry in agentic_nodes.values():
        if isinstance(entry, dict) and entry.get("id") == subagent_id:
            return True
    return False


# ========== Stream Chat ==========


@router.post(
    "/stream",
    summary="Stream Chat Message",
    description="Send chat message with streaming response (Server-Sent Events). "
    "Set subagent_id to route to a specific sub-agent.",
)
async def stream_chat(
    request: StreamChatInput,
    svc: ServiceDep,
    ctx: AppContextDep,
):
    sub_agent_id = request.subagent_id
    if sub_agent_id and not _is_valid_subagent_id(svc, sub_agent_id):
        raise HTTPException(
            status_code=404,
            detail=f"Subagent '{sub_agent_id}' not found",
        )

    async def generate_sse():
        datasource = request.database or svc.agent_config.current_datasource
        session_id = request.session_id
        assistant_message = ""
        run_id = uuid.uuid4().hex

        async def persist_event(event_type: str, payload, event_key: str, role: str = "assistant"):
            if not session_id:
                return
            svc.chat.persist_pi_event(
                session_id,
                event_type,
                payload,
                user_id=ctx.user_id,
                role=role,
                event_id=f"{run_id}:{event_key}",
            )

        async for event in svc.pi_runtime.stream_chat(request, datasource=datasource):
            if event.event == "session":
                session_id = event.data.session_id
                await persist_event(
                    "agent_start",
                    {"run_id": run_id, "mode": "stream", "runtime_variant": request.runtime_variant},
                    "agent_start",
                )
            elif event.event == "message":
                for content in event.data.payload.content:
                    content_payload = dict(content.payload or {})
                    if content.type == "call-tool":
                        await persist_event("tool_execution_start", content_payload, f"tool_start:{event.id}")
                    elif content.type == "call-tool-result":
                        await persist_event("tool_execution_end", content_payload, f"tool_end:{event.id}")
                    elif content.type == "progress":
                        await persist_event("progress", content_payload, f"progress:{event.id}")
                    elif content.type == "error":
                        await persist_event("error", content_payload, f"error:{event.id}")
                    if content.type not in {"markdown", "text"}:
                        continue
                    text = content.payload.get("content")
                    if text is None:
                        text = content.payload.get("text")
                    if isinstance(text, str) and text.strip():
                        assistant_message = text
                        await persist_event(
                            "assistant_answer",
                            {"content": text, "format": content.type},
                            f"assistant_answer:{event.id}",
                        )
                        break
            elif event.event == "error":
                await persist_event(
                    "error",
                    event.data.model_dump(mode="json"),
                    f"error:{event.id}",
                )
                await persist_event(
                    "agent_end",
                    {
                        "run_id": run_id,
                        "status": "error",
                        "termination_reason": event.data.error_type,
                        "has_answer": bool(assistant_message),
                    },
                    f"agent_end:error:{event.id}",
                )
            elif event.event == "end":
                if not session_id or not assistant_message:
                    if session_id:
                        await persist_event(
                            "error",
                            {"code": "missing_assistant_answer", "message": "Pi runtime completed without a persistable chat exchange."},
                            f"error:missing-answer:{event.id}",
                        )
                        await persist_event(
                            "agent_end",
                            {"run_id": run_id, "status": "error", "termination_reason": "missing_assistant_answer"},
                            f"agent_end:missing-answer:{event.id}",
                        )
                    error_event = SSEEvent(
                        id=event.id,
                        event="error",
                        data=SSEErrorData(
                            error="Pi runtime completed without a persistable chat exchange.",
                            error_type="SESSION_PERSISTENCE_ERROR",
                            session_id=session_id,
                        ),
                    )
                    yield f"id: {error_event.id}\nevent: {error_event.event}\ndata: {error_event.data.model_dump_json()}\n\n"
                    return
                try:
                    await svc.chat.persist_pi_exchange(
                        session_id,
                        request.message,
                        assistant_message,
                        user_id=ctx.user_id,
                    )
                except Exception:
                    logger.exception("Failed to persist Pi chat exchange")
                    try:
                        await persist_event(
                            "error",
                            {"code": "session_persistence_error", "message": "The answer was generated, but chat history could not be saved."},
                            f"error:persist:{event.id}",
                        )
                    except Exception:
                        logger.exception("Failed to persist Pi persistence error event")
                    error_event = SSEEvent(
                        id=event.id,
                        event="error",
                        data=SSEErrorData(
                            error="The answer was generated, but chat history could not be saved.",
                            error_type="SESSION_PERSISTENCE_ERROR",
                            session_id=session_id,
                        ),
                    )
                    yield f"id: {error_event.id}\nevent: {error_event.event}\ndata: {error_event.data.model_dump_json()}\n\n"
                    return
                await persist_event(
                    "agent_end",
                    {
                        "run_id": run_id,
                        "status": "success",
                        "has_answer": True,
                        "action_count": event.data.action_count,
                    },
                    "agent_end",
                )

            yield f"id: {event.id}\nevent: {event.event}\ndata: {event.data.model_dump_json()}\n\n"

    return StreamingResponse(generate_sse(), media_type="text/event-stream", headers=_sse_headers())


# ========== Reaction-triggered Feedback ==========


@router.post(
    "/feedback",
    summary="Stream Feedback Agent (reaction-triggered)",
    description=(
        "Trigger the feedback agent from a reaction event (IM emoji, UI thumbs, etc.). "
        "The server builds the canonical user prompt from reaction_emoji/reference_msg/reaction_msg "
        "and routes the request to the feedback sub-agent, which copies the source session and archives reusable knowledge."
    ),
)
async def stream_chat_feedback(
    request: FeedbackChatInput,
    svc: ServiceDep,
    ctx: AppContextDep,
):
    rendered_message = build_reaction_feedback_prompt(
        reaction_emoji=request.reaction_emoji,
        reference_msg=request.reference_msg,
        reaction_msg=request.reaction_msg,
    )
    stream_input = StreamChatInput(
        **request.model_dump(
            exclude={"message", "reaction_emoji", "reference_msg", "reaction_msg"},
        ),
        message=rendered_message,
        subagent_id="feedback",
    )

    async def generate_sse():
        async for event in svc.chat.stream_chat(stream_input, sub_agent_id="feedback", user_id=ctx.user_id):
            yield f"id: {event.id}\nevent: {event.event}\ndata: {event.data.model_dump_json()}\n\n"

    return StreamingResponse(generate_sse(), media_type="text/event-stream", headers=_sse_headers())


# ========== Resume Chat ==========


@router.post(
    "/resume",
    summary="Resume Chat Session",
    description="Reconnect to a running chat task and consume events from a given cursor",
)
async def resume_chat(
    request: ResumeChatInput,
    svc: ServiceDep,
):
    task_manager = svc.task_manager
    task = task_manager.get_task(request.session_id)
    if task is None:
        return Result[dict](
            success=False,
            errorCode="TASK_NOT_FOUND",
            errorMessage="Task not found or already completed. Use the history API to retrieve messages.",
        )

    async def generate_sse():
        async for event in task_manager.consume_events(task, start_from=request.from_event_id):
            yield f"id: {event.id}\nevent: {event.event}\ndata: {event.data.model_dump_json()}\n\n"

    return StreamingResponse(generate_sse(), media_type="text/event-stream", headers=_sse_headers())


# ========== Stop Chat ==========


@router.post(
    "/stop",
    response_model=Result[dict],
    summary="Stop Chat Session",
    description="Stop a currently running chat session",
)
async def stop_chat(
    request: StopChatInput,
    svc: ServiceDep,
) -> Result[dict]:
    stopped = await svc.task_manager.stop_task(request.session_id)
    if stopped:
        return Result[dict](success=True, data={"session_id": request.session_id, "stopped": True})
    return Result[dict](
        success=False,
        errorCode="SESSION_NOT_RUNNING",
        errorMessage=f"Session {request.session_id} is not currently running",
    )


# ========== Session Management ==========


@router.post(
    "/sessions/{session_id}/compact",
    response_model=Result[CompactSessionData],
    summary="Compact Chat Session",
    description="Compact chat session by summarizing conversation history",
)
async def compact_chat_session(
    session_id: Annotated[str, Path(description="Session ID to compact")],
    svc: ServiceDep,
    ctx: AppContextDep,
) -> Result[CompactSessionData]:
    return await svc.chat.compact_session(CompactSessionInput(session_id=session_id), user_id=ctx.user_id)


@router.get(
    "/sessions",
    response_model=Result[ChatSessionData],
    summary="List Chat Sessions",
    description=(
        "List chat sessions. Pass subagent_id to filter by agent "
        "(use 'chat' for the default chat agent, or any builtin/custom subagent id). "
        "Omit to return every session for the user."
    ),
)
async def list_sessions(
    svc: ServiceDep,
    ctx: AppContextDep,
    subagent_id: Optional[str] = Query(
        default=None,
        description="Filter by subagent id; 'chat' selects the default chat agent",
    ),
) -> Result[ChatSessionData]:
    return svc.chat.list_sessions(user_id=ctx.user_id, subagent_id=subagent_id)


@router.delete(
    "/sessions/{session_id}",
    response_model=Result[ChatSessionData],
    summary="Delete Chat Session",
    description="Delete a chat session by ID",
)
async def delete_session(
    session_id: Annotated[str, Path(description="Session ID to delete")],
    svc: ServiceDep,
    ctx: AppContextDep,
) -> Result[ChatSessionData]:
    return svc.chat.delete_session(session_id, user_id=ctx.user_id)


# ========== Chat History (GET /api/v1/history/chat?session_id=xxx) ==========


@router.get(
    "/history",
    response_model=Result[ChatHistoryData],
    summary="Get Chat History",
    description="Get full conversation messages for a chat session",
)
async def get_chat_history(
    svc: ServiceDep,
    ctx: AppContextDep,
    session_id: str = Query(..., description="Session ID to retrieve history for"),
) -> Result[ChatHistoryData]:
    return svc.chat.get_history(session_id, user_id=ctx.user_id)


# ========== Current Chat Model ==========


@router.get(
    "/model",
    response_model=Result[ChatModelData],
    summary="Get Current Chat Model",
    description="Return the active chat model identity (type and model)",
)
async def get_chat_model(
    svc: ServiceDep,
) -> Result[ChatModelData]:
    return svc.chat.get_model()


# ========== User Interaction ==========


@router.post(
    "/user_interaction",
    response_model=Result[dict],
    summary="Submit User Interaction",
    description="Submit user's choice or input for an interactive dialog",
)
async def submit_user_interaction(
    request: UserInteractionInput,
    svc: ServiceDep,
) -> Result[dict]:
    task_manager = svc.task_manager
    task = task_manager.get_task(request.session_id)
    if task is None or task.node is None:
        return Result[dict](
            success=False,
            errorCode="SESSION_NOT_FOUND",
            errorMessage="No active task found for this session",
        )

    broker = task.node.interaction_broker
    if not broker:
        return Result[dict](
            success=False,
            errorCode="BROKER_NOT_FOUND",
            errorMessage="Interaction broker not found for this session",
        )

    # Validate: each answer must be non-empty
    if not request.input or any(len(ans) == 0 for ans in request.input):
        return Result[dict](
            success=False,
            errorCode="INVALID_INPUT",
            errorMessage="Each answer must contain at least one value",
        )

    # Convert List[List[str]] → broker format
    # Single-element lists unwrap to string, multi-element stay as list
    answers = [ans[0] if len(ans) == 1 else ans for ans in request.input]
    if len(answers) == 1:
        answer = answers[0]
        user_choice = json.dumps(answer) if isinstance(answer, list) else answer
    else:
        user_choice = json.dumps(answers)
    success = await broker.submit(request.interaction_key, user_choice)
    return Result[dict](
        success=success,
        data={"interaction_key": request.interaction_key, "submitted": success},
    )


# ========== Tool Result ==========


@router.post(
    "/tool_result",
    response_model=Result[ToolResultData],
    summary="Submit Tool Execution Result",
    description="Receive tool execution result from frontend after filesystem operation",
)
async def submit_tool_result(
    request: ToolResultInput,
    svc: ServiceDep,
) -> Result[ToolResultData]:
    """Receive tool execution result from frontend."""
    task_manager = svc.task_manager
    task = task_manager.get_task(request.session_id) if request.session_id else None
    if not task or not task.node:
        return Result[ToolResultData](
            success=False,
            errorCode="TASK_NOT_FOUND",
            errorMessage="No active task found for this session",
        )

    await task.node.tool_channel.publish(request.call_tool_id, request.tool_result.model_dump())
    return Result[ToolResultData](
        success=True,
        data=ToolResultData(call_tool_id=request.call_tool_id, status="received"),
    )


# ========== Helpers ==========


def _sse_headers() -> dict:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "text/event-stream; charset=utf-8",
    }
