const SECOND = 1000
const MINUTE = 60 * SECOND
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR
const WEEK = 7 * DAY
const MONTH = 30 * DAY
const YEAR = 365 * DAY

export function formatCompactRelativeTime(value: string | Date, now = new Date()) {
  const date = value instanceof Date ? value : new Date(value)
  const timestamp = date.getTime()

  if (!Number.isFinite(timestamp)) return ''

  const diff = Math.max(0, now.getTime() - timestamp)

  if (diff < MINUTE) return 'now'
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m`
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h`
  if (diff < WEEK) return `${Math.floor(diff / DAY)}d`
  if (diff < MONTH) return `${Math.floor(diff / WEEK)}w`
  if (diff < YEAR) return `${Math.floor(diff / MONTH)}mo`

  return `${Math.floor(diff / YEAR)}y`
}
