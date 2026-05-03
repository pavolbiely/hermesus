"""FastAPI route registration for the web-chat API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from hermes_state import SessionDB

from . import file_previews, session_handlers
from .read_aloud_summaries import generate_read_aloud_summary
from .tts import stream_speech_response, synthesize_speech_response
from .models import (
    CreateSessionRequest,
    DeleteSessionResponse,
    DirectorySuggestionsResponse,
    EditMessageRequest,
    ExecuteCommandRequest,
    ExecuteCommandResponse,
    FilePreviewRequest,
    FilePreviewResolveRequest,
    GenerateCommitMessageRequest,
    GitStatusResponse,
    CommitMessageSuggestion,
    ReadAloudSummaryRequest,
    ReadAloudSummaryResponse,
    RenameSessionRequest,
    ReorderWorkspacesRequest,
    RespondRunPromptRequest,
    RespondRunPromptResponse,
    SaveWorkspaceRequest,
    SessionDetailResponse,
    SessionListResponse,
    StartRunRequest,
    StartRunResponse,
    SteerRunRequest,
    SynthesizeSpeechRequest,
    SteerRunResponse,
    StopRunResponse,
    SwitchProfileRequest,
    SwitchProfileResponse,
    UploadAttachmentsResponse,
    WebChatAppUpdateStatusResponse,
    WebChatAttachment,
    WebChatCapabilitiesResponse,
    WebChatCommand,
    WebChatCommandsResponse,
    WebChatFilePreview,
    WebChatFilePreviewReference,
    WebChatMessage,
    WebChatModelCapability,
    WebChatProviderUsageResponse,
    WebChatProfilesResponse,
    WebChatSession,
    WebChatSessionPreviewResponse,
    WebChatUpdateStatusResponse,
    WebChatWorkspace,
    WebChatWorkspaceChanges,
    WebChatWorkspaceResponse,
    WebChatWorkspacesResponse,
)


@dataclass(frozen=True)
class WebChatRouteServices:
    db: Callable[[], SessionDB]
    run_manager: Callable[[], Any]
    web_chat_source: str
    max_session_limit: int
    max_attachments_per_request: int
    list_non_empty_sessions: Callable[[SessionDB, int, int, bool], list[dict[str, Any]]]
    serialize_session: Callable[[dict[str, Any]], WebChatSession]
    serialize_messages: Callable[..., list[WebChatMessage]]
    web_chat_commands: Callable[[], list[WebChatCommand]]
    execute_web_chat_command: Callable[[ExecuteCommandRequest], ExecuteCommandResponse]
    persist_command_exchange: Callable[[ExecuteCommandRequest, ExecuteCommandResponse], ExecuteCommandResponse]
    default_model_id: Callable[[], str | None]
    active_provider_id: Callable[[], str]
    model_capabilities: Callable[[], list[WebChatModelCapability]]
    provider_usage: Callable[[str | None, str | None], WebChatProviderUsageResponse]
    list_web_chat_profiles: Callable[[], WebChatProfilesResponse]
    switch_web_chat_profile: Callable[[SwitchProfileRequest], SwitchProfileResponse]
    list_web_chat_workspaces: Callable[[], WebChatWorkspacesResponse]
    directory_suggestions: Callable[[str], list[str]]
    create_managed_workspace: Callable[[SaveWorkspaceRequest], WebChatWorkspace]
    update_managed_workspace: Callable[[str, SaveWorkspaceRequest], WebChatWorkspace]
    reorder_managed_workspaces: Callable[[ReorderWorkspacesRequest], list[WebChatWorkspace]]
    delete_managed_workspace: Callable[[str], None]
    store_upload: Callable[[UploadFile, str | None], Awaitable[WebChatAttachment]]
    load_attachment: Callable[[str, str | None], WebChatAttachment]
    validate_workspace: Callable[[str | None], Path | None]
    workspace_changes: Callable[[str | None], WebChatWorkspaceChanges]
    git_status: Callable[[str | None], GitStatusResponse]
    generate_commit_message: Callable[[GenerateCommitMessageRequest], CommitMessageSuggestion]
    hidden_agent_response: Callable[..., str]
    title_from_message: Callable[[str], str]
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]]
    edit_user_message: Callable[[SessionDB, str, str, str], None]
    delete_session_git_changes: Callable[[SessionDB, str], None]
    remove_session_worktree: Callable[[SessionDB, str], None]
    duplicate_session: Callable[[SessionDB, str], SessionDetailResponse]
    get_session_preview: Callable[[SessionDB, str], WebChatSessionPreviewResponse]
    generate_session_preview: Callable[[SessionDB, str], WebChatSessionPreviewResponse]
    session_git_changes_by_message: Callable[[SessionDB, str], dict[str, WebChatWorkspaceChanges]]
    isolated_worktree_for_session: Callable[[SessionDB, str], Any | None]
    update_status: Callable[[], WebChatUpdateStatusResponse]
    perform_update: Callable[[], WebChatUpdateStatusResponse]
    app_update_status: Callable[[], WebChatAppUpdateStatusResponse]
    perform_app_update: Callable[[], WebChatAppUpdateStatusResponse]


def register_web_chat_routes(router: APIRouter, services: WebChatRouteServices) -> None:
    @router.get("/sessions", response_model=SessionListResponse)
    def list_sessions(
        limit: int = Query(default=50, ge=1, le=services.max_session_limit),
        offset: int = Query(default=0, ge=0),
        includeArchived: bool = Query(default=False),
    ) -> SessionListResponse:
        return session_handlers.list_sessions_response(
            services.db(),
            limit=limit,
            offset=offset,
            include_archived=includeArchived,
            list_non_empty_sessions=services.list_non_empty_sessions,
            serialize_session=services.serialize_session,
        )

    @router.get("/commands", response_model=WebChatCommandsResponse)
    def list_commands() -> WebChatCommandsResponse:
        return WebChatCommandsResponse(commands=services.web_chat_commands())

    @router.post("/commands/execute", response_model=ExecuteCommandResponse, response_model_exclude_none=True)
    def execute_command(payload: ExecuteCommandRequest) -> ExecuteCommandResponse:
        return services.persist_command_exchange(payload, services.execute_web_chat_command(payload))

    @router.get("/capabilities", response_model=WebChatCapabilitiesResponse)
    def get_capabilities() -> WebChatCapabilitiesResponse:
        models = services.model_capabilities()
        default_model = services.default_model_id()
        default_capability = next((model for model in models if model.id == default_model), None) or (models[0] if models else None)
        return WebChatCapabilitiesResponse(
            provider=services.active_provider_id(),
            defaultModel=default_model or (default_capability.id if default_capability else None),
            defaultProvider=default_capability.provider if default_capability else services.active_provider_id(),
            models=models,
        )

    @router.get("/provider-usage", response_model=WebChatProviderUsageResponse, response_model_exclude_none=True)
    def get_provider_usage(
        provider: str | None = Query(default=None, max_length=100),
        model: str | None = Query(default=None, max_length=200),
    ) -> WebChatProviderUsageResponse:
        return services.provider_usage(provider, model)

    @router.get("/update", response_model=WebChatUpdateStatusResponse)
    def get_update_status() -> WebChatUpdateStatusResponse:
        return services.update_status()

    @router.post("/update", response_model=WebChatUpdateStatusResponse)
    def update_hermes() -> WebChatUpdateStatusResponse:
        return services.perform_update()

    @router.get("/app-update", response_model=WebChatAppUpdateStatusResponse)
    def get_app_update_status() -> WebChatAppUpdateStatusResponse:
        return services.app_update_status()

    @router.post("/app-update", response_model=WebChatAppUpdateStatusResponse)
    def update_app() -> WebChatAppUpdateStatusResponse:
        return services.perform_app_update()

    @router.post("/tts")
    def synthesize_speech(payload: SynthesizeSpeechRequest) -> FileResponse:
        return synthesize_speech_response(payload.text, voice=payload.voice, speed=payload.speed)

    @router.post("/tts/stream", response_model=None)
    def stream_speech(payload: SynthesizeSpeechRequest) -> FileResponse | StreamingResponse:
        return stream_speech_response(payload.text, speed=payload.speed)

    @router.post("/read-aloud-summary", response_model=ReadAloudSummaryResponse)
    def summarize_read_aloud(payload: ReadAloudSummaryRequest) -> ReadAloudSummaryResponse:
        return ReadAloudSummaryResponse(
            text=generate_read_aloud_summary(
                payload.text,
                hidden_agent=services.hidden_agent_response,
                model=payload.model,
                provider=payload.provider,
                reasoning_effort=payload.reasoningEffort,
            )
        )

    @router.get("/profiles", response_model=WebChatProfilesResponse)
    def get_profiles() -> WebChatProfilesResponse:
        return services.list_web_chat_profiles()

    @router.post("/profiles/active", response_model=SwitchProfileResponse)
    def switch_profile(payload: SwitchProfileRequest) -> SwitchProfileResponse:
        return services.switch_web_chat_profile(payload)

    @router.get("/workspaces", response_model=WebChatWorkspacesResponse)
    def get_workspaces() -> WebChatWorkspacesResponse:
        return services.list_web_chat_workspaces()

    @router.get("/workspace-directories", response_model=DirectorySuggestionsResponse)
    def get_workspace_directories(prefix: str = Query(min_length=1, max_length=4096)) -> DirectorySuggestionsResponse:
        return DirectorySuggestionsResponse(suggestions=services.directory_suggestions(prefix))

    @router.post("/workspaces", status_code=status.HTTP_201_CREATED, response_model=WebChatWorkspaceResponse)
    def create_workspace(payload: SaveWorkspaceRequest) -> WebChatWorkspaceResponse:
        return WebChatWorkspaceResponse(workspace=services.create_managed_workspace(payload))

    @router.patch("/workspaces/order", response_model=WebChatWorkspacesResponse)
    def reorder_workspaces(payload: ReorderWorkspacesRequest) -> WebChatWorkspacesResponse:
        return WebChatWorkspacesResponse(workspaces=services.reorder_managed_workspaces(payload), activeWorkspace=None)

    @router.patch("/workspaces/{workspace_id}", response_model=WebChatWorkspaceResponse)
    def update_workspace(workspace_id: str, payload: SaveWorkspaceRequest) -> WebChatWorkspaceResponse:
        return WebChatWorkspaceResponse(workspace=services.update_managed_workspace(workspace_id, payload))

    @router.delete("/workspaces/{workspace_id}", response_model=DeleteSessionResponse)
    def delete_workspace(workspace_id: str) -> DeleteSessionResponse:
        services.delete_managed_workspace(workspace_id)
        return DeleteSessionResponse(ok=True)

    @router.post("/attachments", status_code=status.HTTP_201_CREATED, response_model=UploadAttachmentsResponse)
    async def upload_attachments(
        files: list[UploadFile] = File(...),
        workspace: str | None = Form(default=None),
    ) -> UploadAttachmentsResponse:
        if len(files) > services.max_attachments_per_request:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many attachments")
        return UploadAttachmentsResponse(attachments=[await services.store_upload(file, workspace) for file in files])

    @router.get("/attachments/{attachment_id}", response_model=WebChatAttachment)
    def get_attachment(attachment_id: str, workspace: str | None = None) -> WebChatAttachment:
        return services.load_attachment(attachment_id, workspace)

    @router.get("/attachments/{attachment_id}/content")
    def get_attachment_content(attachment_id: str, workspace: str | None = None) -> FileResponse:
        attachment = services.load_attachment(attachment_id, workspace)
        path = Path(attachment.path)
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment file not found")
        return FileResponse(path, media_type=attachment.mediaType, filename=attachment.name, content_disposition_type="inline")

    @router.get("/workspace-changes", response_model=WebChatWorkspaceChanges, response_model_exclude_none=True)
    def get_workspace_changes(workspace: str | None = None) -> WebChatWorkspaceChanges:
        validated = services.validate_workspace(workspace)
        return services.workspace_changes(str(validated) if validated else None)

    @router.get("/git/status", response_model=GitStatusResponse)
    def get_git_status(workspace: str | None = None) -> GitStatusResponse:
        validated = services.validate_workspace(workspace)
        return services.git_status(str(validated) if validated else None)


    @router.post("/git/commit-message", response_model=CommitMessageSuggestion)
    def generate_git_commit_message(payload: GenerateCommitMessageRequest) -> CommitMessageSuggestion:
        validated = services.validate_workspace(payload.workspace)
        payload.workspace = str(validated) if validated else None
        return services.generate_commit_message(payload)

    @router.post("/file-preview", response_model=WebChatFilePreview, response_model_exclude_none=True)
    def get_file_preview(payload: FilePreviewRequest) -> WebChatFilePreview:
        return file_previews.preview_file(
            payload.path,
            payload.workspace,
            validate_workspace=services.validate_workspace,
        )

    @router.post("/file-preview/resolve", response_model=list[WebChatFilePreviewReference], response_model_exclude_none=True)
    def resolve_file_preview_paths(payload: FilePreviewResolveRequest) -> list[WebChatFilePreviewReference]:
        return file_previews.resolve_existing_files(
            payload.paths,
            payload.workspace,
            validate_workspace=services.validate_workspace,
        )

    @router.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionDetailResponse)
    def create_session(payload: CreateSessionRequest) -> SessionDetailResponse:
        return session_handlers.create_session_response(
            services.db(),
            payload=payload,
            web_chat_source=services.web_chat_source,
            title_from_message=services.title_from_message,
            get_session_or_404=services.get_session_or_404,
            serialize_session=services.serialize_session,
            serialize_messages=services.serialize_messages,
        )

    @router.patch("/sessions/{session_id}", response_model=SessionDetailResponse)
    def rename_session(session_id: str, payload: RenameSessionRequest) -> SessionDetailResponse:
        return session_handlers.rename_session_response(
            services.db(),
            session_id=session_id,
            payload=payload,
            get_session_or_404=services.get_session_or_404,
            serialize_session=services.serialize_session,
            serialize_messages=services.serialize_messages,
            validate_workspace=services.validate_workspace,
        )

    @router.patch("/sessions/{session_id}/messages/{message_id}", response_model=SessionDetailResponse)
    def edit_message(session_id: str, message_id: str, payload: EditMessageRequest) -> SessionDetailResponse:
        return session_handlers.edit_message_response(
            services.db(),
            session_id=session_id,
            message_id=message_id,
            payload=payload,
            get_session_or_404=services.get_session_or_404,
            edit_user_message=services.edit_user_message,
            serialize_session=services.serialize_session,
            serialize_messages=services.serialize_messages,
        )

    @router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
    def delete_session(session_id: str) -> DeleteSessionResponse:
        return session_handlers.delete_session_response(
            services.db(),
            session_id=session_id,
            delete_session_git_changes=services.delete_session_git_changes,
            remove_session_worktree=services.remove_session_worktree,
        )

    @router.post("/sessions/{session_id}/duplicate", status_code=status.HTTP_201_CREATED, response_model=SessionDetailResponse)
    def duplicate_session(session_id: str) -> SessionDetailResponse:
        return services.duplicate_session(services.db(), session_id)

    @router.get("/sessions/{session_id}/preview", response_model=WebChatSessionPreviewResponse)
    def get_session_preview(session_id: str) -> WebChatSessionPreviewResponse:
        return services.get_session_preview(services.db(), session_id)

    @router.post("/sessions/{session_id}/preview-summary", response_model=WebChatSessionPreviewResponse)
    def generate_session_preview(session_id: str) -> WebChatSessionPreviewResponse:
        return services.generate_session_preview(services.db(), session_id)

    @router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
    def get_session(
        session_id: str,
        includeWorkspaceChanges: bool = Query(default=False),
        messageLimit: int | None = Query(default=None, ge=1, le=200),
        messageBefore: str | None = Query(default=None, min_length=1),
    ) -> SessionDetailResponse:
        return session_handlers.get_session_response(
            services.db(),
            session_id=session_id,
            include_workspace_changes=includeWorkspaceChanges,
            message_limit=messageLimit,
            message_before=messageBefore,
            get_session_or_404=services.get_session_or_404,
            session_git_changes_by_message=services.session_git_changes_by_message,
            serialize_session=services.serialize_session,
            serialize_messages=services.serialize_messages,
            active_run_for_session=services.run_manager().active_run_for_session,
            recover_interrupted_run_for_session=services.run_manager().recover_interrupted_run_for_session,
            isolated_worktree_for_session=services.isolated_worktree_for_session,
        )

    @router.post("/runs", status_code=status.HTTP_202_ACCEPTED, response_model=StartRunResponse)
    def start_run(payload: StartRunRequest) -> StartRunResponse:
        return services.run_manager().start(payload)

    @router.get("/runs/{run_id}/events")
    def run_events(
        run_id: str,
        after: int | None = Query(default=None, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        event_after = after
        if event_after is None and last_event_id and last_event_id.isdigit():
            event_after = int(last_event_id)
        return StreamingResponse(
            services.run_manager().events(run_id, after=event_after),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/runs/{run_id}/prompts/{prompt_id}/response", response_model=RespondRunPromptResponse)
    def respond_run_prompt(run_id: str, prompt_id: str, payload: RespondRunPromptRequest) -> RespondRunPromptResponse:
        return services.run_manager().respond_prompt(run_id, prompt_id, payload)

    @router.post("/runs/{run_id}/steer", response_model=SteerRunResponse)
    def steer_run(run_id: str, payload: SteerRunRequest) -> SteerRunResponse:
        return services.run_manager().steer(run_id, payload)

    @router.post("/runs/{run_id}/stop", response_model=StopRunResponse)
    def stop_run(run_id: str) -> StopRunResponse:
        return services.run_manager().stop(run_id)
