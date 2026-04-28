"""FastAPI route registration for the web-chat API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from hermes_state import SessionDB

from . import file_previews, session_handlers
from .models import (
    CreateSessionRequest,
    DeleteSessionResponse,
    DirectorySuggestionsResponse,
    EditMessageRequest,
    ExecuteCommandRequest,
    ExecuteCommandResponse,
    FilePreviewRequest,
    RenameSessionRequest,
    RespondRunPromptRequest,
    RespondRunPromptResponse,
    SaveWorkspaceRequest,
    SessionDetailResponse,
    SessionListResponse,
    StartRunRequest,
    StartRunResponse,
    SteerRunRequest,
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
    WebChatMessage,
    WebChatModelCapability,
    WebChatProfilesResponse,
    WebChatSession,
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
    list_non_empty_sessions: Callable[[SessionDB, int, int], list[dict[str, Any]]]
    serialize_session: Callable[[dict[str, Any]], WebChatSession]
    serialize_messages: Callable[..., list[WebChatMessage]]
    web_chat_commands: Callable[[], list[WebChatCommand]]
    execute_web_chat_command: Callable[[ExecuteCommandRequest], ExecuteCommandResponse]
    persist_command_exchange: Callable[[ExecuteCommandRequest, ExecuteCommandResponse], ExecuteCommandResponse]
    default_model_id: Callable[[], str | None]
    active_provider_id: Callable[[], str]
    model_capabilities: Callable[[], list[WebChatModelCapability]]
    list_web_chat_profiles: Callable[[], WebChatProfilesResponse]
    switch_web_chat_profile: Callable[[SwitchProfileRequest], SwitchProfileResponse]
    list_web_chat_workspaces: Callable[[], WebChatWorkspacesResponse]
    directory_suggestions: Callable[[str], list[str]]
    create_managed_workspace: Callable[[SaveWorkspaceRequest], WebChatWorkspace]
    update_managed_workspace: Callable[[str, SaveWorkspaceRequest], WebChatWorkspace]
    delete_managed_workspace: Callable[[str], None]
    store_upload: Callable[[UploadFile, str | None], Awaitable[WebChatAttachment]]
    load_attachment: Callable[[str, str | None], WebChatAttachment]
    validate_workspace: Callable[[str | None], Path | None]
    workspace_changes: Callable[[str | None], WebChatWorkspaceChanges]
    title_from_message: Callable[[str], str]
    get_session_or_404: Callable[[SessionDB, str], dict[str, Any]]
    edit_user_message: Callable[[SessionDB, str, str, str], None]
    delete_session_git_changes: Callable[[SessionDB, str], None]
    remove_session_worktree: Callable[[SessionDB, str], None]
    duplicate_session: Callable[[SessionDB, str], SessionDetailResponse]
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
    ) -> SessionListResponse:
        return session_handlers.list_sessions_response(
            services.db(),
            limit=limit,
            offset=offset,
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
        return WebChatCapabilitiesResponse(
            provider=services.active_provider_id(),
            defaultModel=services.default_model_id(),
            models=services.model_capabilities(),
        )

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

    @router.post("/file-preview", response_model=WebChatFilePreview, response_model_exclude_none=True)
    def get_file_preview(payload: FilePreviewRequest) -> WebChatFilePreview:
        return file_previews.preview_file(
            payload.path,
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

    @router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
    def get_session(session_id: str, includeWorkspaceChanges: bool = Query(default=False)) -> SessionDetailResponse:
        return session_handlers.get_session_response(
            services.db(),
            session_id=session_id,
            include_workspace_changes=includeWorkspaceChanges,
            get_session_or_404=services.get_session_or_404,
            session_git_changes_by_message=services.session_git_changes_by_message,
            serialize_session=services.serialize_session,
            serialize_messages=services.serialize_messages,
            active_run_for_session=services.run_manager().active_run_for_session,
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
