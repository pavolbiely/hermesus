"""Native web chat API for the Hermes dashboard.

This module exposes JSON/SSE endpoints for a first-class web chat UI. It keeps
``SessionDB`` as the source of truth and intentionally does not use the legacy
xterm/PTY dashboard chat transport.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from hermes_state import SessionDB

router = APIRouter(prefix="/api/web-chat", tags=["web-chat"])

WEB_CHAT_SOURCE = "web-chat"
MAX_SESSION_LIMIT = 100
MAX_ATTACHMENTS_PER_REQUEST = 8
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
MAX_PATCH_BYTES_PER_FILE = 96 * 1024
MAX_PATCH_BYTES_PER_RUN = 512 * 1024
_KNOWN_ATTACHMENT_ROOTS: set[Path] = set()
_PROJECT_SETTINGS_LOCK = threading.Lock()


from .web_chat_modules.agent_runner import (
    agent_executor as _agent_executor_impl,
    conversation_history_for_agent as _conversation_history_for_agent_impl,
)
from .web_chat_modules.attachments import (
    attachment_metadata_roots as _attachment_metadata_roots_impl,
    attachment_root as _attachment_root_impl,
    attachment_url as _attachment_url_impl,
    attachment_with_runtime_state as _attachment_with_runtime_state_impl,
    input_with_attachment_context as _input_with_attachment_context_impl,
    is_safe_attachment_id as _is_safe_attachment_id_impl,
    load_attachment as _load_attachment_impl,
    resolve_attachments as _resolve_attachments_impl,
    safe_filename as _safe_filename_impl,
    store_upload as _store_upload_impl,
    unique_attachment_path as _unique_attachment_path_impl,
    attachment_meta_path as _attachment_meta_path_impl,
)

from .web_chat_modules.capabilities import (
    available_model_ids as _available_model_ids_impl,
    default_model_id as _default_model_id_impl,
    default_reasoning_effort as _default_reasoning_effort_impl,
    model_capabilities as _model_capabilities_impl,
    model_reasoning_efforts as _model_reasoning_efforts_impl,
    resolve_codex_access_token as _resolve_codex_access_token_impl,
    resolve_requested_model as _resolve_requested_model_impl,
    resolve_requested_reasoning_effort as _resolve_requested_reasoning_effort_impl,
)
from .web_chat_modules.git_changes import (
    copy_session_git_changes as _copy_session_git_changes_impl,
    count_text_lines as _count_text_lines_impl,
    delete_session_git_changes as _delete_session_git_changes_impl,
    delete_session_git_changes_after_message as _delete_session_git_changes_after_message_impl,
    ensure_git_change_schema as _ensure_git_change_schema_impl,
    file_patch as _file_patch_impl,
    git_name_statuses as _git_name_statuses_impl,
    git_status_porcelain as _git_status_porcelain_impl,
    git_untracked_files as _git_untracked_files_impl,
    is_git_tracked as _is_git_tracked_impl,
    record_session_git_changes as _record_session_git_changes_impl,
    session_git_changes_by_message as _session_git_changes_by_message_impl,
    status_paths as _status_paths_impl,
    untracked_file_patch as _untracked_file_patch_impl,
    workspace_changes as _workspace_changes_impl,
    workspace_changes_since as _workspace_changes_since_impl,
    workspace_patch as _workspace_patch_impl,
    workspace_root as _workspace_root_impl,
)
from .web_chat_modules.commands import (
    execute_changes_command as _execute_changes_command_impl,
    execute_help_command as _execute_help_command_impl,
    execute_status_command as _execute_status_command_impl,
    execute_web_chat_command as _execute_web_chat_command_impl,
    message_text as _message_text_impl,
    persist_command_exchange as _persist_command_exchange_impl,
    transient_assistant_message as _transient_assistant_message_impl,
    web_chat_command as _web_chat_command_impl,
    web_chat_commands as _web_chat_commands_impl,
)
from .web_chat_modules.models import (
    CreateSessionRequest,
    DeleteSessionResponse,
    DirectorySuggestionsResponse,
    EditMessageRequest,
    ExecuteCommandRequest,
    ExecuteCommandResponse,
    RenameSessionRequest,
    SaveWorkspaceRequest,
    SessionDetailResponse,
    SessionListResponse,
    StartRunRequest,
    StartRunResponse,
    StopRunResponse,
    SwitchProfileRequest,
    SwitchProfileResponse,
    UploadAttachmentsResponse,
    WebChatAttachment,
    WebChatCapabilitiesResponse,
    WebChatCommand,
    WebChatCommandsResponse,
    WebChatFileChange,
    WebChatMessage,
    WebChatModelCapability,
    WebChatPart,
    WebChatProfile,
    WebChatProfilesResponse,
    WebChatSession,
    WebChatWorkspace,
    WebChatWorkspaceChanges,
    WebChatWorkspaceResponse,
    WebChatWorkspacesResponse,
)

from .web_chat_modules.profiles import (
    list_web_chat_profiles as _list_web_chat_profiles_impl,
    profile_dependencies as _profile_dependencies_impl,
    restart_backend_soon as _restart_backend_soon_impl,
    switch_web_chat_profile as _switch_web_chat_profile_impl,
    validate_profile as _validate_profile_impl,
)
from .web_chat_modules.run_manager import RunContext, RunManager as _RunManager, RunManagerServices
from .web_chat_modules.session_mutations import (
    duplicate_session as _duplicate_session_impl,
    list_non_empty_sessions as _list_non_empty_sessions_impl,
    set_session_title_safely as _set_session_title_safely_impl,
    title_from_message as _title_from_message_impl,
    unique_copy_title as _unique_copy_title_impl,
)
from .web_chat_modules.message_mutations import (
    edit_user_message as _edit_user_message_impl,
    validate_edited_message_continuation as _validate_edited_message_continuation_impl,
)
from .web_chat_modules.sessions import (
    attach_tool_output as _attach_tool_output_impl,
    get_session_or_404 as _get_session_or_404_impl,
    iso_from_epoch as _iso_from_epoch_impl,
    message_attachments as _message_attachments_impl,
    message_parts as _message_parts_impl,
    parse_jsonish as _parse_jsonish_impl,
    serialize_message as _serialize_message_impl,
    serialize_messages as _serialize_messages_impl,
    serialize_session as _serialize_session_impl,
    session_model_config as _session_model_config_impl,
    session_reasoning_effort as _session_reasoning_effort_impl,
    session_workspace as _session_workspace_impl,
    tool_call_id as _tool_call_id_impl,
    tool_call_name as _tool_call_name_impl,
)
from .web_chat_modules.workspaces import (
    create_managed_workspace as _create_managed_workspace_impl,
    delete_managed_workspace as _delete_managed_workspace_impl,
    empty_project_settings as _empty_project_settings_impl,
    ensure_workspace_schema as _ensure_workspace_schema_impl,
    find_managed_workspace_by_path as _find_managed_workspace_by_path_impl,
    get_managed_workspace as _get_managed_workspace_impl,
    list_managed_workspaces as _list_managed_workspaces_impl,
    load_project_settings as _load_project_settings_impl,
    normalize_workspace_path as _normalize_workspace_path_impl,
    project_root as _project_root_impl,
    project_web_chat_settings_path as _project_web_chat_settings_path_impl,
    read_legacy_db_workspaces as _read_legacy_db_workspaces_impl,
    update_managed_workspace as _update_managed_workspace_impl,
    validate_workspace as _validate_workspace_impl,
    default_workspace as _default_workspace_impl,
    directory_suggestions as _directory_suggestions_impl,
    list_web_chat_workspaces as _list_web_chat_workspaces_impl,
    workspace_label as _workspace_label_impl,
    workspace_entries as _workspace_entries_impl,
    workspace_from_mapping as _workspace_from_mapping_impl,
    write_project_settings as _write_project_settings_impl,
)



def _agent_executor(context: RunContext, emit: Callable[[dict[str, Any]], None]) -> str:
    return _agent_executor_impl(context, emit, conversation_history=_conversation_history_for_agent)


def _conversation_history_for_agent(session_id: str) -> list[dict[str, str]]:
    return _conversation_history_for_agent_impl(_db, session_id)


def _db() -> SessionDB:
    return SessionDB()


def _ensure_workspace_schema(db: SessionDB) -> None:
    _ensure_workspace_schema_impl(db)


def _workspace_from_row(row: Any) -> WebChatWorkspace:
    return _workspace_from_mapping(row)


def _workspace_from_mapping(value: Any) -> WebChatWorkspace:
    return _workspace_from_mapping_impl(value)


def _normalize_workspace_path(path: str) -> Path:
    return _normalize_workspace_path_impl(path)


def _project_root() -> Path:
    return _project_root_impl()


def _project_web_chat_settings_path() -> Path:
    return _project_web_chat_settings_path_impl()


def _empty_project_settings() -> dict[str, Any]:
    return _empty_project_settings_impl()


def _read_legacy_db_workspaces(db: SessionDB | None = None) -> list[WebChatWorkspace]:
    return _read_legacy_db_workspaces_impl(_db, db)


def _load_project_settings() -> dict[str, Any]:
    return _load_project_settings_impl(_db)


def _write_project_settings(settings: dict[str, Any]) -> None:
    _write_project_settings_impl(settings)


def _workspace_entries(settings: dict[str, Any]) -> list[dict[str, str]]:
    return _workspace_entries_impl(settings)


def _list_managed_workspaces(db: SessionDB | None = None) -> list[WebChatWorkspace]:
    return _list_managed_workspaces_impl(_db, _PROJECT_SETTINGS_LOCK, db)


def _find_managed_workspace_by_path(path: Path, db: SessionDB | None = None) -> WebChatWorkspace | None:
    return _find_managed_workspace_by_path_impl(path, _db, _PROJECT_SETTINGS_LOCK, db)


def _get_managed_workspace(workspace_id: str, db: SessionDB | None = None) -> WebChatWorkspace:
    return _get_managed_workspace_impl(workspace_id, _db, _PROJECT_SETTINGS_LOCK, db)


def _create_managed_workspace(request: SaveWorkspaceRequest) -> WebChatWorkspace:
    return _create_managed_workspace_impl(request, _db, _PROJECT_SETTINGS_LOCK)


def _update_managed_workspace(workspace_id: str, request: SaveWorkspaceRequest) -> WebChatWorkspace:
    return _update_managed_workspace_impl(workspace_id, request, _db, _PROJECT_SETTINGS_LOCK)


def _delete_managed_workspace(workspace_id: str) -> None:
    _delete_managed_workspace_impl(workspace_id, _db, _PROJECT_SETTINGS_LOCK)

def _ensure_git_change_schema(db: SessionDB) -> None:
    _ensure_git_change_schema_impl(db)


def _record_session_git_changes(
    db: SessionDB,
    *,
    session_id: str,
    run_id: str | None,
    message_id: int | None,
    workspace: str,
    baseline_status: str | None,
    final_status: str,
    changes: WebChatWorkspaceChanges,
) -> None:
    _record_session_git_changes_impl(
        db,
        session_id=session_id,
        run_id=run_id,
        message_id=message_id,
        workspace=workspace,
        baseline_status=baseline_status,
        final_status=final_status,
        changes=changes,
    )


def _session_git_changes_by_message(db: SessionDB, session_id: str) -> dict[str, WebChatWorkspaceChanges]:
    return _session_git_changes_by_message_impl(db, session_id, iso_from_epoch=_iso_from_epoch)


def _copy_session_git_changes(
    db: SessionDB,
    *,
    source_session_id: str,
    target_session_id: str,
    message_id_map: dict[int, int],
) -> None:
    _copy_session_git_changes_impl(
        db,
        source_session_id=source_session_id,
        target_session_id=target_session_id,
        message_id_map=message_id_map,
        record_changes=_record_session_git_changes,
    )


def _delete_session_git_changes(db: SessionDB, session_id: str) -> None:
    _delete_session_git_changes_impl(db, session_id)


def _delete_session_git_changes_after_message(db: SessionDB, session_id: str, message_id: int) -> None:
    _delete_session_git_changes_after_message_impl(db, session_id, message_id)


def _edit_user_message(db: SessionDB, session_id: str, message_id: str, content: str) -> None:
    _edit_user_message_impl(
        db,
        session_id,
        message_id,
        content,
        delete_git_changes_after_message=_delete_session_git_changes_after_message,
    )


def _validate_edited_message_continuation(db: SessionDB, session_id: str, message_id: str) -> None:
    _validate_edited_message_continuation_impl(db, session_id, message_id)


def _persist_run_workspace_changes(context: RunContext, message_id: int | None) -> None:
    if not context.workspace:
        return
    final_status = _git_status_porcelain(context.workspace)
    if final_status is None or final_status == (context.baseline_git_status or ""):
        return

    changes = _workspace_changes_since(context.workspace, context.baseline_git_status or "", context.run_id)
    if not changes.files:
        return
    _record_session_git_changes(
        _db(),
        session_id=context.session_id,
        run_id=context.run_id,
        message_id=message_id,
        workspace=context.workspace,
        baseline_status=context.baseline_git_status or "",
        final_status=final_status,
        changes=changes,
    )


def _git_status_porcelain(workspace: str | None) -> str | None:
    return _git_status_porcelain_impl(workspace, workspace_root_func=_workspace_root)


def _status_paths(status_text: str) -> set[str]:
    return _status_paths_impl(status_text)


def _workspace_changes_since(workspace: str, baseline_status: str, run_id: str | None) -> WebChatWorkspaceChanges:
    return _workspace_changes_since_impl(
        workspace,
        baseline_status,
        run_id,
        workspace_root_func=_workspace_root,
        workspace_changes_func=_workspace_changes,
        workspace_patch_func=_workspace_patch,
    )


def _workspace_patch(root: Path, files: list[WebChatFileChange]) -> tuple[dict[str, Any] | None, bool]:
    return _workspace_patch_impl(
        root,
        files,
        max_patch_bytes_per_file=MAX_PATCH_BYTES_PER_FILE,
        max_patch_bytes_per_run=MAX_PATCH_BYTES_PER_RUN,
    )


def _file_patch(root: Path, file: WebChatFileChange) -> str | None:
    return _file_patch_impl(root, file)


def _is_git_tracked(root: Path, path: str) -> bool:
    return _is_git_tracked_impl(root, path)


def _untracked_file_patch(root: Path, path: str) -> str | None:
    return _untracked_file_patch_impl(root, path)


def _profile_dependencies():
    return _profile_dependencies_impl()


def _list_web_chat_profiles() -> WebChatProfilesResponse:
    return _list_web_chat_profiles_impl(profile_dependencies_func=_profile_dependencies)


def _restart_backend_soon() -> None:
    return _restart_backend_soon_impl()


def _switch_web_chat_profile(payload: SwitchProfileRequest) -> SwitchProfileResponse:
    return _switch_web_chat_profile_impl(
        payload,
        has_running_runs=run_manager.has_running_runs,
        restart_backend=_restart_backend_soon,
        profile_dependencies_func=_profile_dependencies,
    )


def _validate_profile(profile: str | None) -> str | None:
    return _validate_profile_impl(profile, profile_dependencies_func=_profile_dependencies)


def _workspace_label(path: Path) -> str:
    return _workspace_label_impl(path)


def _validate_workspace(workspace: str | None) -> Path | None:
    return _validate_workspace_impl(
        workspace,
        find_managed_workspace_by_path_func=_find_managed_workspace_by_path,
        workspace_root_func=_workspace_root,
    )


def _list_web_chat_workspaces() -> WebChatWorkspacesResponse:
    return _list_web_chat_workspaces_impl(_list_managed_workspaces)


def _directory_suggestions(prefix: str, *, limit: int = 300) -> list[str]:
    return _directory_suggestions_impl(prefix, limit=limit)


def _default_workspace() -> Path | None:
    return _default_workspace_impl(_list_web_chat_workspaces)


def _attachment_root(workspace: str | None = None) -> Path:
    return _attachment_root_impl(workspace, validate_workspace=_validate_workspace)


def _is_safe_attachment_id(attachment_id: str) -> bool:
    return _is_safe_attachment_id_impl(attachment_id)


def _safe_filename(filename: str | None) -> str:
    return _safe_filename_impl(filename)


def _unique_attachment_path(root: Path, filename: str) -> Path:
    return _unique_attachment_path_impl(root, filename)


def _attachment_meta_path(path: Path) -> Path:
    return _attachment_meta_path_impl(path)


def _attachment_url(attachment_id: str) -> str:
    return _attachment_url_impl(attachment_id)


def _attachment_with_runtime_state(attachment: WebChatAttachment) -> WebChatAttachment:
    return _attachment_with_runtime_state_impl(attachment)


def _attachment_metadata_roots(workspace: str | None = None) -> list[Path]:
    return _attachment_metadata_roots_impl(
        workspace,
        known_roots=_KNOWN_ATTACHMENT_ROOTS,
        validate_workspace=_validate_workspace,
        list_workspaces=_list_web_chat_workspaces,
    )


def _load_attachment(attachment_id: str, workspace: str | None = None) -> WebChatAttachment:
    return _load_attachment_impl(
        attachment_id,
        workspace,
        known_roots=_KNOWN_ATTACHMENT_ROOTS,
        validate_workspace=_validate_workspace,
        list_workspaces=_list_web_chat_workspaces,
    )


def _resolve_attachments(ids: list[str] | None, workspace: str | None = None) -> list[WebChatAttachment]:
    return _resolve_attachments_impl(
        ids,
        workspace,
        known_roots=_KNOWN_ATTACHMENT_ROOTS,
        validate_workspace=_validate_workspace,
        list_workspaces=_list_web_chat_workspaces,
    )


def _input_with_attachment_context(input_text: str, attachments: list[WebChatAttachment]) -> str:
    return _input_with_attachment_context_impl(input_text, attachments)


async def _store_upload(file: UploadFile, workspace: str | None = None) -> WebChatAttachment:
    return await _store_upload_impl(
        file,
        workspace,
        max_attachment_bytes=MAX_ATTACHMENT_BYTES,
        known_roots=_KNOWN_ATTACHMENT_ROOTS,
        validate_workspace=_validate_workspace,
    )

def _web_chat_commands() -> list[WebChatCommand]:
    return _web_chat_commands_impl()


def _web_chat_command(command_id: str) -> WebChatCommand:
    return _web_chat_command_impl(command_id)


def _transient_assistant_message(text: str) -> WebChatMessage:
    return _transient_assistant_message_impl(text, iso_now=_iso_now)


def _execute_help_command() -> ExecuteCommandResponse:
    return _execute_help_command_impl(iso_now=_iso_now)


def _execute_status_command(request: ExecuteCommandRequest) -> ExecuteCommandResponse:
    return _execute_status_command_impl(request, iso_now=_iso_now)


def _execute_changes_command(request: ExecuteCommandRequest) -> ExecuteCommandResponse:
    return _execute_changes_command_impl(
        request,
        iso_now=_iso_now,
        validate_workspace=_validate_workspace,
        workspace_changes=_workspace_changes,
    )


def _execute_web_chat_command(request: ExecuteCommandRequest) -> ExecuteCommandResponse:
    return _execute_web_chat_command_impl(
        request,
        iso_now=_iso_now,
        validate_workspace=_validate_workspace,
        workspace_changes=_workspace_changes,
    )


def _message_text(message: WebChatMessage) -> str:
    return _message_text_impl(message)


def _persist_command_exchange(request: ExecuteCommandRequest, response: ExecuteCommandResponse) -> ExecuteCommandResponse:
    return _persist_command_exchange_impl(
        request,
        response,
        db_factory=_db,
        get_session_or_404=_get_session_or_404,
        title_from_message=_title_from_message,
        validate_workspace=_validate_workspace,
        record_session_git_changes=_record_session_git_changes,
        git_status_porcelain=_git_status_porcelain,
        serialize_message=_serialize_message,
        web_chat_source=WEB_CHAT_SOURCE,
    )


def _title_from_message(message: str) -> str:
    return _title_from_message_impl(message)


def _set_session_title_safely(db: SessionDB, session_id: str, title: str) -> None:
    _set_session_title_safely_impl(db, session_id, title)


def _unique_copy_title(db: SessionDB, title: str | None, session_id: str) -> str:
    return _unique_copy_title_impl(db, title, session_id)


def _duplicate_session(db: SessionDB, session_id: str) -> SessionDetailResponse:
    return _duplicate_session_impl(
        db,
        session_id,
        get_session_or_404=_get_session_or_404,
        parse_jsonish=_parse_jsonish,
        copy_session_git_changes=_copy_session_git_changes,
        session_git_changes_by_message=_session_git_changes_by_message,
        serialize_session=_serialize_session,
        serialize_messages=_serialize_messages,
        web_chat_source=WEB_CHAT_SOURCE,
    )


def _iso_from_epoch(value: Any) -> str:
    return _iso_from_epoch_impl(value)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_jsonish(value: Any) -> Any:
    return _parse_jsonish_impl(value)


def _serialize_session(session: dict[str, Any]) -> WebChatSession:
    return _serialize_session_impl(session)


def _message_attachments(message: dict[str, Any]) -> list[WebChatAttachment]:
    return _message_attachments_impl(message)


def _message_parts(message: dict[str, Any]) -> list[WebChatPart]:
    return _message_parts_impl(message)


def _serialize_message(message: dict[str, Any]) -> WebChatMessage:
    return _serialize_message_impl(message)


def _tool_call_name(tool_call: Any) -> str | None:
    return _tool_call_name_impl(tool_call)


def _tool_call_id(tool_call: Any) -> str | None:
    return _tool_call_id_impl(tool_call)


def _attach_tool_output(messages: list[WebChatMessage], tool_message: dict[str, Any]) -> bool:
    return _attach_tool_output_impl(messages, tool_message)


def _serialize_messages(
    messages: list[dict[str, Any]],
    *,
    changes_by_message: dict[str, WebChatWorkspaceChanges] | None = None,
) -> list[WebChatMessage]:
    return _serialize_messages_impl(messages, changes_by_message=changes_by_message)


def _get_session_or_404(db: SessionDB, session_id: str) -> dict[str, Any]:
    return _get_session_or_404_impl(db, session_id)


def _session_model_config(session: dict[str, Any] | None) -> dict[str, Any]:
    return _session_model_config_impl(session)


def _session_workspace(session: dict[str, Any] | None) -> str | None:
    return _session_workspace_impl(session)


def _session_reasoning_effort(session: dict[str, Any] | None) -> str | None:
    return _session_reasoning_effort_impl(session)


def _resolve_codex_access_token() -> str | None:
    return _resolve_codex_access_token_impl()


def _available_model_ids() -> list[str]:
    return _available_model_ids_impl(resolve_access_token=_resolve_codex_access_token)


def _model_reasoning_efforts(model_id: str | None) -> list[str]:
    return _model_reasoning_efforts_impl(model_id)


def _default_reasoning_effort(model_id: str | None) -> str | None:
    return _default_reasoning_effort_impl(model_id)


def _workspace_root(workspace: str | None = None) -> Path | None:
    return _workspace_root_impl(workspace)


def _workspace_changes(workspace: str | None = None) -> WebChatWorkspaceChanges:
    return _workspace_changes_impl(workspace, workspace_root_func=_workspace_root)


def _git_name_statuses(output: str) -> dict[str, str]:
    return _git_name_statuses_impl(output)


def _git_untracked_files(root: Path) -> list[str]:
    return _git_untracked_files_impl(root)


def _count_text_lines(path: Path) -> int:
    return _count_text_lines_impl(path)


def _model_capabilities() -> list[WebChatModelCapability]:
    return _model_capabilities_impl(available_ids=_available_model_ids)


def _default_model_id() -> str | None:
    return _default_model_id_impl(available_ids=_available_model_ids)


def _resolve_requested_model(model_id: str | None, *, session: dict[str, Any] | None = None) -> str | None:
    return _resolve_requested_model_impl(model_id, session=session, default_model=_default_model_id)


def _resolve_requested_reasoning_effort(
    model_id: str | None,
    reasoning_effort: str | None,
    *,
    session: dict[str, Any] | None = None,
) -> str | None:
    return _resolve_requested_reasoning_effort_impl(
        model_id,
        reasoning_effort,
        session=session,
        session_reasoning_effort=_session_reasoning_effort,
    )


def _list_non_empty_sessions(db: SessionDB, limit: int, offset: int) -> list[dict[str, Any]]:
    return _list_non_empty_sessions_impl(db, limit, offset, max_session_limit=MAX_SESSION_LIMIT)


def _run_manager_services() -> RunManagerServices:
    return RunManagerServices(
        source=WEB_CHAT_SOURCE,
        db=_db,
        resolve_requested_model=lambda requested, session=None: _resolve_requested_model(requested, session=session),
        resolve_requested_reasoning_effort=lambda model, requested, session=None: _resolve_requested_reasoning_effort(model, requested, session=session),
        validate_workspace=_validate_workspace,
        session_workspace=_session_workspace,
        validate_profile=_validate_profile,
        resolve_attachments=_resolve_attachments,
        validate_edited_message_continuation=_validate_edited_message_continuation,
        input_with_attachment_context=_input_with_attachment_context,
        set_session_title_safely=_set_session_title_safely,
        title_from_message=_title_from_message,
        git_status_porcelain=_git_status_porcelain,
        persist_run_workspace_changes=_persist_run_workspace_changes,
        agent_executor=_agent_executor,
    )


def RunManager(executor=None):
    return _RunManager(_run_manager_services(), executor=executor)


run_manager = RunManager()

@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    limit: int = Query(default=50, ge=1, le=MAX_SESSION_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> SessionListResponse:
    db = _db()
    sessions = _list_non_empty_sessions(db, limit=limit, offset=offset)
    return SessionListResponse(sessions=[_serialize_session(session) for session in sessions])


@router.get("/commands", response_model=WebChatCommandsResponse)
def list_commands() -> WebChatCommandsResponse:
    return WebChatCommandsResponse(commands=_web_chat_commands())


@router.post("/commands/execute", response_model=ExecuteCommandResponse, response_model_exclude_none=True)
def execute_command(payload: ExecuteCommandRequest) -> ExecuteCommandResponse:
    return _persist_command_exchange(payload, _execute_web_chat_command(payload))


@router.get("/capabilities", response_model=WebChatCapabilitiesResponse)
def get_capabilities() -> WebChatCapabilitiesResponse:
    return WebChatCapabilitiesResponse(
        provider="codex",
        defaultModel=_default_model_id(),
        models=_model_capabilities(),
    )


@router.get("/profiles", response_model=WebChatProfilesResponse)
def get_profiles() -> WebChatProfilesResponse:
    return _list_web_chat_profiles()


@router.post("/profiles/active", response_model=SwitchProfileResponse)
def switch_profile(payload: SwitchProfileRequest) -> SwitchProfileResponse:
    return _switch_web_chat_profile(payload)


@router.get("/workspaces", response_model=WebChatWorkspacesResponse)
def get_workspaces() -> WebChatWorkspacesResponse:
    return _list_web_chat_workspaces()


@router.get("/workspace-directories", response_model=DirectorySuggestionsResponse)
def get_workspace_directories(prefix: str = Query(min_length=1, max_length=4096)) -> DirectorySuggestionsResponse:
    return DirectorySuggestionsResponse(suggestions=_directory_suggestions(prefix))


@router.post("/workspaces", status_code=status.HTTP_201_CREATED, response_model=WebChatWorkspaceResponse)
def create_workspace(payload: SaveWorkspaceRequest) -> WebChatWorkspaceResponse:
    return WebChatWorkspaceResponse(workspace=_create_managed_workspace(payload))


@router.patch("/workspaces/{workspace_id}", response_model=WebChatWorkspaceResponse)
def update_workspace(workspace_id: str, payload: SaveWorkspaceRequest) -> WebChatWorkspaceResponse:
    return WebChatWorkspaceResponse(workspace=_update_managed_workspace(workspace_id, payload))


@router.delete("/workspaces/{workspace_id}", response_model=DeleteSessionResponse)
def delete_workspace(workspace_id: str) -> DeleteSessionResponse:
    _delete_managed_workspace(workspace_id)
    return DeleteSessionResponse(ok=True)


@router.post("/attachments", status_code=status.HTTP_201_CREATED, response_model=UploadAttachmentsResponse)
async def upload_attachments(
    files: list[UploadFile] = File(...),
    workspace: str | None = Form(default=None),
) -> UploadAttachmentsResponse:
    if len(files) > MAX_ATTACHMENTS_PER_REQUEST:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Too many attachments")
    return UploadAttachmentsResponse(attachments=[await _store_upload(file, workspace) for file in files])


@router.get("/attachments/{attachment_id}", response_model=WebChatAttachment)
def get_attachment(attachment_id: str, workspace: str | None = None) -> WebChatAttachment:
    return _load_attachment(attachment_id, workspace)


@router.get("/attachments/{attachment_id}/content")
def get_attachment_content(attachment_id: str, workspace: str | None = None) -> FileResponse:
    attachment = _load_attachment(attachment_id, workspace)
    path = Path(attachment.path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment file not found")
    return FileResponse(path, media_type=attachment.mediaType, filename=attachment.name, content_disposition_type="inline")


@router.get("/workspace-changes", response_model=WebChatWorkspaceChanges, response_model_exclude_none=True)
def get_workspace_changes(workspace: str | None = None) -> WebChatWorkspaceChanges:
    validated = _validate_workspace(workspace)
    return _workspace_changes(str(validated) if validated else None)



@router.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionDetailResponse)
def create_session(payload: CreateSessionRequest) -> SessionDetailResponse:
    db = _db()
    session_id = uuid4().hex
    title = _title_from_message(payload.message)

    db.create_session(session_id, source=WEB_CHAT_SOURCE)
    db.set_session_title(session_id, title)
    db.append_message(session_id, "user", payload.message)

    session = _get_session_or_404(db, session_id)
    messages = db.get_messages(session_id)
    return SessionDetailResponse(
        session=_serialize_session(session),
        messages=_serialize_messages(messages),
    )


@router.patch("/sessions/{session_id}", response_model=SessionDetailResponse)
def rename_session(session_id: str, payload: RenameSessionRequest) -> SessionDetailResponse:
    db = _db()
    _get_session_or_404(db, session_id)
    try:
        db.set_session_title(session_id, payload.title)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session = _get_session_or_404(db, session_id)
    return SessionDetailResponse(
        session=_serialize_session(session),
        messages=_serialize_messages(db.get_messages(session_id)),
    )


@router.patch("/sessions/{session_id}/messages/{message_id}", response_model=SessionDetailResponse)
def edit_message(session_id: str, message_id: str, payload: EditMessageRequest) -> SessionDetailResponse:
    db = _db()
    _get_session_or_404(db, session_id)
    _edit_user_message(db, session_id, message_id, payload.content)
    session = _get_session_or_404(db, session_id)
    return SessionDetailResponse(
        session=_serialize_session(session),
        messages=_serialize_messages(db.get_messages(session_id)),
    )


@router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
def delete_session(session_id: str) -> DeleteSessionResponse:
    db = _db()
    if not db.delete_session(session_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    _delete_session_git_changes(db, session_id)
    return DeleteSessionResponse(ok=True)


@router.post("/sessions/{session_id}/duplicate", status_code=status.HTTP_201_CREATED, response_model=SessionDetailResponse)
def duplicate_session(session_id: str) -> SessionDetailResponse:
    return _duplicate_session(_db(), session_id)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str, includeWorkspaceChanges: bool = Query(default=False)) -> SessionDetailResponse:
    db = _db()
    session = _get_session_or_404(db, session_id)
    messages = db.get_messages(session_id)
    changes_by_message = _session_git_changes_by_message(db, session_id) if includeWorkspaceChanges else None
    return SessionDetailResponse(
        session=_serialize_session(session),
        messages=_serialize_messages(messages, changes_by_message=changes_by_message),
    )


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED, response_model=StartRunResponse)
def start_run(payload: StartRunRequest) -> StartRunResponse:
    return run_manager.start(payload)


@router.get("/runs/{run_id}/events")
def run_events(run_id: str) -> StreamingResponse:
    return StreamingResponse(run_manager.events(run_id), media_type="text/event-stream")


@router.post("/runs/{run_id}/stop", response_model=StopRunResponse)
def stop_run(run_id: str) -> StopRunResponse:
    return run_manager.stop(run_id)
