"""Pydantic request and response models for the native web chat API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WebChatAttachment(BaseModel):
    id: str
    name: str
    mediaType: str
    size: int
    path: str
    workspace: str | None = None
    relativePath: str | None = None
    url: str | None = None
    exists: bool = True


class WebChatPart(BaseModel):
    type: Literal["text", "reasoning", "tool", "media", "approval", "changes"]
    text: str | None = None
    name: str | None = None
    status: str | None = None
    input: Any | None = None
    output: Any | None = None
    url: str | None = None
    mediaType: str | None = None
    approvalId: str | None = None
    changes: Any | None = None
    attachments: list[WebChatAttachment] | None = None


class WebChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system", "tool"]
    parts: list[WebChatPart]
    createdAt: str
    reasoning: str | None = None
    toolName: str | None = None
    toolCalls: Any | None = None


class WebChatSession(BaseModel):
    id: str
    title: str | None
    preview: str
    source: str | None
    model: str | None
    reasoningEffort: str | None = None
    workspace: str | None = None
    messageCount: int
    createdAt: str
    updatedAt: str


class WebChatModelCapability(BaseModel):
    id: str
    label: str
    reasoningEfforts: list[str]
    defaultReasoningEffort: str | None = None


class WebChatCapabilitiesResponse(BaseModel):
    provider: str
    defaultModel: str | None
    models: list[WebChatModelCapability]


class WebChatCommand(BaseModel):
    id: str
    name: str
    description: str
    usage: str
    safety: Literal["safe", "confirmation_required", "blocked"] = "safe"
    requiresWorkspace: bool = False
    requiresSession: bool = False


class WebChatCommandsResponse(BaseModel):
    commands: list[WebChatCommand]


class ExecuteCommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=120)
    sessionId: str | None = None
    workspace: str | None = None
    model: str | None = None
    reasoningEffort: str | None = None


class ExecuteCommandResponse(BaseModel):
    commandId: str
    handled: bool = True
    sessionId: str | None = None
    message: WebChatMessage | None = None
    changes: "WebChatWorkspaceChanges | None" = None


class WebChatFileChange(BaseModel):
    path: str
    status: str
    additions: int
    deletions: int


class WebChatWorkspaceChanges(BaseModel):
    files: list[WebChatFileChange]
    totalFiles: int
    totalAdditions: int
    totalDeletions: int
    workspace: str | None = None
    runId: str | None = None
    capturedAt: str | None = None
    patch: dict[str, Any] | None = None
    patchTruncated: bool | None = None


class WebChatProfile(BaseModel):
    id: str
    label: str
    path: str
    active: bool = False


class WebChatProfilesResponse(BaseModel):
    profiles: list[WebChatProfile]
    activeProfile: str


class SwitchProfileRequest(BaseModel):
    profile: str = Field(min_length=1, max_length=64)
    restart: bool = True


class SwitchProfileResponse(BaseModel):
    profiles: list[WebChatProfile]
    activeProfile: str
    restarting: bool = False


class WebChatWorkspace(BaseModel):
    id: str
    label: str
    path: str
    active: bool = False


class WebChatWorkspacesResponse(BaseModel):
    workspaces: list[WebChatWorkspace]
    activeWorkspace: str | None = None


class WebChatWorkspaceResponse(BaseModel):
    workspace: WebChatWorkspace


class SaveWorkspaceRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=4096)


class DirectorySuggestionsResponse(BaseModel):
    suggestions: list[str]


class UploadAttachmentsResponse(BaseModel):
    attachments: list[WebChatAttachment]


class SessionListResponse(BaseModel):
    sessions: list[WebChatSession]


class SessionDetailResponse(BaseModel):
    session: WebChatSession
    messages: list[WebChatMessage]


class CreateSessionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=65536)


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class EditMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=65536)


class DeleteSessionResponse(BaseModel):
    ok: bool


class StartRunRequest(BaseModel):
    sessionId: str | None = None
    input: str = Field(min_length=1, max_length=65536)
    workspace: str | None = None
    profile: str | None = None
    attachments: list[str] | None = None
    editedMessageId: str | None = None
    model: str | None = None
    reasoningEffort: str | None = None
    provider: str | None = None
    enabledToolsets: list[str] | None = None


class StartRunResponse(BaseModel):
    sessionId: str
    runId: str


class StopRunResponse(BaseModel):
    runId: str
    stopped: bool
