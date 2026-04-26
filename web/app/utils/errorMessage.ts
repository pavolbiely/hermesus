export function getHermesErrorMessage(err: unknown, fallback: string) {
  if (typeof err === 'object' && err && 'data' in err) {
    const data = (err as { data?: { detail?: unknown } }).data
    if (typeof data?.detail === 'string' && data.detail.trim()) return data.detail
  }

  return err instanceof Error && err.message ? err.message : fallback
}
