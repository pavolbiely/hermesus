export type AcpBridgeHealth = {
  command: string
  args: string[]
  cwd: string
  initialized: boolean
  running: boolean
  pid?: number
  lastExit?: { code: number | null, signal: NodeJS.Signals | null }
  lastError?: string
  stderr: string[]
}
