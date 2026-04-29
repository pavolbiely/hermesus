"""Pydantic request and response models for the native web chat API."""

from __future__ import annotations

from datetime import datetime, timezone
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


class FilePreviewRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    workspace: str | None = None


class FilePreviewResolveRequest(BaseModel):
    paths: list[str] = Field(default_factory=list, max_length=100)
    workspace: str | None = None


class WebChatFilePreviewReference(BaseModel):
    path: str
    requestedPath: str
    relativePath: str | None = None
    name: str
    mediaType: str
    size: int
    language: str | None = None
    exists: bool = True


class WebChatFilePreview(BaseModel):
    path: str
    requestedPath: str
    relativePath: str | None = None
    name: str
    mediaType: str
    size: int
    language: str | None = None
    content: str | None = None
    truncated: bool = False
    previewable: bool = True
    reason: str | None = None


class WebChatPromptChoice(BaseModel):
    id: str
    label: str
    description: str | None = None
    style: Literal["neutral", "primary", "warning", "error"] = "neutral"


class WebChatPrompt(BaseModel):
    id: str
    runId: str
    sessionId: str
    kind: Literal["approval", "question"]
    title: str
    description: str | None = None
    detail: str | None = None
    detailType: Literal["text", "command", "json"] = "text"
    choices: list[WebChatPromptChoice] = Field(default_factory=list)
    freeText: bool = False
    status: Literal["pending", "answered", "expired", "cancelled"] = "pending"
    selectedChoice: str | None = None
    responseText: str | None = None
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    answeredAt: str | None = None
    expiresAt: str | None = None


class RespondRunPromptRequest(BaseModel):
    choice: str | None = None
    text: str | None = None


class RespondRunPromptResponse(BaseModel):
    prompt: WebChatPrompt


class WebChatTaskPlanItem(BaseModel):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed", "cancelled"] = "pending"


class WebChatTaskPlan(BaseModel):
    items: list[WebChatTaskPlanItem]
    updatedAt: str | None = None


class WebChatPart(BaseModel):
    type: Literal["text", "reasoning", "tool", "media", "interactive_prompt", "changes", "steer", "status", "event", "task_plan"]
    text: str | None = None
    name: str | None = None
    status: str | None = None
    eventType: str | None = None
    severity: str | None = None
    title: str | None = None
    description: str | None = None
    occurredAt: str | None = None
    input: Any | None = None
    output: Any | None = None
    url: str | None = None
    mediaType: str | None = None
    approvalId: str | None = None
    prompt: WebChatPrompt | None = None
    taskPlan: WebChatTaskPlan | None = None
    changes: Any | None = None
    attachments: list[WebChatAttachment] | None = None
    metadata: dict[str, Any] | None = None


class WebChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system", "tool"]
    parts: list[WebChatPart]
    createdAt: str
    clientMessageId: str | None = None
    tokenCount: int | None = None
    inputTokens: int | None = None
    outputTokens: int | None = None
    cacheReadTokens: int | None = None
    cacheWriteTokens: int | None = None
    reasoningTokens: int | None = None
    apiCalls: int | None = None
    generationDurationMs: int | None = None
    modelDurationMs: int | None = None
    toolDurationMs: int | None = None
    promptWaitDurationMs: int | None = None
    reasoning: str | None = None
    toolName: str | None = None
    toolCalls: Any | None = None


class WebChatSession(BaseModel):
    id: str
    title: str | None
    preview: str
    source: str | None
    model: str | None
    provider: str | None = None
    reasoningEffort: str | None = None
    workspace: str | None = None
    pinned: bool = False
    messageCount: int
    createdAt: str
    updatedAt: str


class WebChatModelCapability(BaseModel):
    id: str
    label: str
    reasoningEfforts: list[str]
    defaultReasoningEffort: str | None = None
    contextWindowTokens: int | None = None
    autoCompressTokens: int | None = None
    provider: str | None = None
    providerLabel: str | None = None


class WebChatCapabilitiesResponse(BaseModel):
    provider: str
    defaultModel: str | None
    defaultProvider: str | None = None
    models: list[WebChatModelCapability]


class WebChatProviderUsageWindow(BaseModel):
    label: str
    usedPercent: float
    remainingPercent: float
    windowMinutes: int | None = None
    resetsAt: str | None = None


class WebChatProviderUsageLimit(BaseModel):
    id: str
    label: str
    windows: list[WebChatProviderUsageWindow] = Field(default_factory=list)


class WebChatProviderUsageResponse(BaseModel):
    provider: str
    model: str | None = None
    source: str
    available: bool
    unavailableReason: str | None = None
    limits: list[WebChatProviderUsageLimit] = Field(default_factory=list)
    capturedAt: str | None = None


class WebChatUpdateStatusResponse(BaseModel):
    updateAvailable: bool
    runtimeOutOfSync: bool
    upstreamPath: str
    runtimePath: str
    branch: str
    currentRevision: str | None = None
    remoteRevision: str | None = None
    runtimeRevision: str | None = None


class WebChatAppUpdateStatusResponse(BaseModel):
    updateAvailable: bool
    appPath: str
    branch: str
    currentRevision: str | None = None
    remoteRevision: str | None = None


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


GitChangeArea = Literal["staged", "unstaged", "untracked"]
GitChangeStatus = Literal["created", "edited", "deleted", "renamed", "copied", "untracked"]


class GitFileSelection(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    area: GitChangeArea


class GitStatusFile(BaseModel):
    path: str
    oldPath: str | None = None
    area: GitChangeArea
    status: GitChangeStatus
    staged: bool = False
    unstaged: bool = False
    untracked: bool = False
    additions: int | None = None
    deletions: int | None = None
    binary: bool = False


class GitStatusResponse(BaseModel):
    workspace: str
    root: str
    head: str | None = None
    branch: str | None = None
    ahead: int | None = None
    behind: int | None = None
    files: list[GitStatusFile]
    hasStagedChanges: bool
    hasUnstagedChanges: bool
    hasUntrackedChanges: bool


class GitDiffFile(BaseModel):
    path: str
    oldPath: str | None = None
    area: GitChangeArea
    status: GitChangeStatus
    patch: str | None = None
    additions: int = 0
    deletions: int = 0
    truncated: bool = False
    binary: bool = False


class GitDiffResponse(BaseModel):
    workspace: str
    root: str
    fingerprint: str
    files: list[GitDiffFile]
    totalAdditions: int
    totalDeletions: int
    truncated: bool = False


class GenerateCommitMessageRequest(BaseModel):
    workspace: str | None = None
    sessionId: str | None = None
    chatContext: str | None = Field(default=None, max_length=20000)
    selection: list[GitFileSelection] = Field(default_factory=list, max_length=200)


class CommitSplitSuggestion(BaseModel):
    subject: str
    paths: list[str]
    reason: str


class CommitMessageSuggestion(BaseModel):
    subject: str
    body: str | None = None
    warnings: list[str] = Field(default_factory=list)
    splitSuggestions: list[CommitSplitSuggestion] = Field(default_factory=list)
    rulesSource: str = "Conventional Commits"
    contextSummary: str = "selected Git changes"


class WebChatIsolatedWorkspace(BaseModel):
    sessionId: str
    sourceWorkspace: str
    sourceGitRoot: str
    worktreePath: str
    branchName: str
    baseRef: str
    status: Literal["active", "applied", "deleted", "missing", "cleaned"] = "active"
    dirty: bool = False


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


class ReorderWorkspacesRequest(BaseModel):
    workspaceIds: list[str]


class DirectorySuggestionsResponse(BaseModel):
    suggestions: list[str]


class UploadAttachmentsResponse(BaseModel):
    attachments: list[WebChatAttachment]


class SessionListResponse(BaseModel):
    sessions: list[WebChatSession]


class ActiveRunSummary(BaseModel):
    runId: str
    sessionId: str
    status: Literal["running", "stopping", "completed", "stopped", "failed"]
    prompts: list[WebChatPrompt] = Field(default_factory=list)


class SessionDetailResponse(BaseModel):
    session: WebChatSession
    messages: list[WebChatMessage]
    activeRun: ActiveRunSummary | None = None
    isolatedWorkspace: WebChatIsolatedWorkspace | None = None
    messagesHasMoreBefore: bool = False
    messagesTotal: int | None = None


class CreateSessionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=65536)


class RenameSessionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    pinned: bool | None = None


class EditMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=65536)


class DeleteSessionResponse(BaseModel):
    ok: bool


class StartRunRequest(BaseModel):
    sessionId: str | None = None
    input: str = Field(min_length=1, max_length=65536)
    clientMessageId: str | None = Field(default=None, max_length=120)
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
    userMessageId: str | None = None


class StopRunResponse(BaseModel):
    runId: str
    stopped: bool


class SteerRunRequest(BaseModel):
    text: str = Field(min_length=1, max_length=65536)


class SteerRunResponse(BaseModel):
    runId: str
    sessionId: str
    accepted: bool = True
    messageId: str | None = None
