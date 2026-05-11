import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { Readable, Writable } from 'node:stream'
import {
  ClientSideConnection,
  PROTOCOL_VERSION,
  ndJsonStream,
  type CancelNotification,
  type Client,
  type CloseSessionRequest,
  type ForkSessionRequest,
  type InitializeResponse,
  type ListSessionsRequest,
  type LoadSessionRequest,
  type NewSessionRequest,
  type PromptRequest,
  type RequestPermissionRequest,
  type RequestPermissionResponse,
  type SessionNotification,
  type SetSessionConfigOptionRequest,
  type SetSessionModeRequest,
  type SetSessionModelRequest
} from '@agentclientprotocol/sdk'
import { publishAcpEvent } from './events'
import { requestAcpPermission } from './permissions'
import { latestReasoningEventFromSessionFile } from './sessionReasoning'
import { recordAcpTurnMetadata } from './turnMetadata'
import type { AcpBridgeHealth } from './types'

const activePromptBySession = new Map<string, { turnId: string, messageId: string }>()
const activeThoughtTurns = new Set<string>()

type BridgeRuntimeConfig = {
  hermesAcpCommand?: string
  hermesAcpArgs?: string[] | string
  hermesAcpCwd?: string
}

class AcpBridge {
  private child: ChildProcessWithoutNullStreams | null = null
  private connection: ClientSideConnection | null = null
  private initializePromise: Promise<InitializeResponse> | null = null
  private initialized = false
  private stderrLines: string[] = []
  private lastExit: AcpBridgeHealth['lastExit']
  private lastError: string | undefined

  health(config: BridgeRuntimeConfig): AcpBridgeHealth {
    const { command, args, cwd } = bridgeConfig(config)
    return {
      command,
      args,
      cwd,
      initialized: this.initialized,
      running: Boolean(this.child && !this.child.killed && this.child.exitCode === null),
      pid: this.child?.pid,
      lastExit: this.lastExit,
      lastError: this.lastError,
      stderr: [...this.stderrLines]
    }
  }

  async initialize(config: BridgeRuntimeConfig) {
    if (this.initialized && this.initializePromise) return this.initializePromise
    if (this.initializePromise) return this.initializePromise

    this.start(config)
    if (!this.connection) throw new Error('ACP connection was not created')

    this.initializePromise = this.connection.initialize({
      protocolVersion: PROTOCOL_VERSION,
      clientInfo: { name: 'Hermesum', version: '0.1.0' },
      clientCapabilities: {}
    }).then((response) => {
      this.initialized = true
      return response
    }).catch((error: unknown) => {
      this.lastError = error instanceof Error ? error.message : String(error)
      this.resetConnection()
      throw error
    })

    return this.initializePromise
  }

  async listSessions(config: BridgeRuntimeConfig, params: ListSessionsRequest) {
    const connection = await this.readyConnection(config)
    return connection.listSessions(params)
  }

  activePrompt(sessionId: string) {
    return activePromptBySession.get(sessionId) || null
  }

  async newSession(config: BridgeRuntimeConfig, params: NewSessionRequest) {
    const connection = await this.readyConnection(config)
    return connection.newSession(params)
  }

  async loadSession(config: BridgeRuntimeConfig, params: LoadSessionRequest) {
    const connection = await this.readyConnection(config)
    return connection.loadSession(params)
  }

  async forkSession(config: BridgeRuntimeConfig, params: ForkSessionRequest) {
    const connection = await this.readyConnection(config)
    return connection.unstable_forkSession(params)
  }

  async closeSession(config: BridgeRuntimeConfig, params: CloseSessionRequest) {
    const connection = await this.readyConnection(config)
    return connection.closeSession(params)
  }

  async setSessionMode(config: BridgeRuntimeConfig, params: SetSessionModeRequest) {
    const connection = await this.readyConnection(config)
    return connection.setSessionMode(params)
  }

  async setSessionModel(config: BridgeRuntimeConfig, params: SetSessionModelRequest) {
    const connection = await this.readyConnection(config)
    return connection.unstable_setSessionModel(params)
  }

  async setSessionConfigOption(config: BridgeRuntimeConfig, params: SetSessionConfigOptionRequest) {
    const connection = await this.readyConnection(config)
    return connection.setSessionConfigOption(params)
  }

  async prompt(config: BridgeRuntimeConfig, params: PromptRequest, turnId: string) {
    const connection = await this.readyConnection(config)
    const messageId = params.messageId || crypto.randomUUID()
    const promptParams: PromptRequest = { ...params, messageId }

    activePromptBySession.set(params.sessionId, { turnId, messageId })
    publishAcpEvent({ type: 'prompt.started', sessionId: params.sessionId, turnId, messageId, message: firstTextContent(params.prompt) })

    try {
      const response = await connection.prompt(promptParams)
      const userMessageId = response.userMessageId || messageId
      const completedAt = new Date().toISOString()
      try {
        await recordAcpTurnMetadata(config, params.sessionId, {
          turnId,
          userMessageId,
          completedAt,
          usage: response.usage ?? null
        })
      } catch (error) {
        console.warn('Failed to persist ACP turn metadata', error)
      }
      const active = activePromptBySession.get(params.sessionId)
      if (active?.turnId !== turnId) return response
      try {
        if (!activeThoughtTurns.has(turnId)) {
          const reasoningEvent = await latestReasoningEventFromSessionFile(config, params.sessionId, turnId)
          if (reasoningEvent) publishAcpEvent(reasoningEvent)
        }
      } catch (error) {
        console.warn('Failed to restore ACP reasoning summary', error)
      }
      publishAcpEvent({ type: 'prompt.completed', sessionId: params.sessionId, turnId, messageId, userMessageId, completedAt, response })
      return response
    } catch (error: unknown) {
      const active = activePromptBySession.get(params.sessionId)
      if (active?.turnId === turnId) {
        const message = error instanceof Error ? error.message : String(error)
        publishAcpEvent({ type: 'prompt.failed', sessionId: params.sessionId, turnId, messageId, error: message })
      }
      throw error
    } finally {
      const active = activePromptBySession.get(params.sessionId)
      if (active?.turnId === turnId) activePromptBySession.delete(params.sessionId)
      activeThoughtTurns.delete(turnId)
    }
  }

  async cancel(config: BridgeRuntimeConfig, params: CancelNotification) {
    const connection = await this.readyConnection(config)
    const active = activePromptBySession.get(params.sessionId)
    await connection.cancel(params)
    if (!active) return
    activePromptBySession.delete(params.sessionId)
    activeThoughtTurns.delete(active.turnId)
    publishAcpEvent({
      type: 'prompt.cancelled',
      sessionId: params.sessionId,
      turnId: active.turnId,
      messageId: active.messageId
    })
  }

  private async readyConnection(config: BridgeRuntimeConfig) {
    await this.initialize(config)
    if (!this.connection) throw new Error('ACP connection was not created')
    return this.connection
  }

  private start(config: BridgeRuntimeConfig) {
    if (this.child && this.connection && this.child.exitCode === null) return

    const { command, args, cwd } = bridgeConfig(config)
    this.lastError = undefined
    this.lastExit = undefined
    this.stderrLines = []

    const child = spawn(command, args, {
      cwd,
      env: process.env,
      stdio: ['pipe', 'pipe', 'pipe']
    })

    child.stderr.on('data', (chunk: Buffer) => {
      this.recordStderr(chunk.toString('utf8'))
    })

    child.on('error', (error) => {
      this.lastError = error.message
      this.resetConnection()
    })

    child.on('exit', (code, signal) => {
      this.lastExit = { code, signal }
      this.resetConnection()
    })

    const input = Writable.toWeb(child.stdin) as WritableStream<Uint8Array>
    const output = Readable.toWeb(child.stdout) as ReadableStream<Uint8Array>
    const stream = ndJsonStream(input, output)

    this.child = child
    this.connection = new ClientSideConnection(() => createClientHandler(), stream)
  }

  private recordStderr(output: string) {
    for (const line of output.split(/\r?\n/)) {
      const trimmed = line.trim()
      if (trimmed) this.stderrLines.push(trimmed)
    }
    this.stderrLines = this.stderrLines.slice(-50)
  }

  private resetConnection() {
    this.initialized = false
    this.initializePromise = null
    this.connection = null
    this.child = null
  }
}

function createClientHandler(): Client {
  return {
    async sessionUpdate(params: SessionNotification) {
      const active = activePromptBySession.get(params.sessionId)
      if (active && params.update.sessionUpdate === 'agent_thought_chunk') {
        activeThoughtTurns.add(active.turnId)
      }
      publishAcpEvent({
        type: 'session.update',
        sessionId: params.sessionId,
        notification: params,
        turnId: active?.turnId,
        messageId: active?.messageId
      })
    },
    async requestPermission(params: RequestPermissionRequest): Promise<RequestPermissionResponse> {
      return requestAcpPermission(params)
    }
  }
}

function firstTextContent(prompt: PromptRequest['prompt']) {
  const block = prompt.find(item => item.type === 'text')
  return block && 'text' in block && typeof block.text === 'string' ? block.text : undefined
}

function bridgeConfig(config: BridgeRuntimeConfig) {
  const command = config.hermesAcpCommand || 'hermes'
  const args = Array.isArray(config.hermesAcpArgs)
    ? config.hermesAcpArgs
    : typeof config.hermesAcpArgs === 'string'
      ? config.hermesAcpArgs.split(' ').filter(Boolean)
      : ['acp']
  const cwd = config.hermesAcpCwd || process.cwd()
  return { command, args, cwd }
}

const bridge = new AcpBridge()

export function getAcpBridge() {
  return bridge
}
