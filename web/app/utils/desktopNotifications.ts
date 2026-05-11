export type DesktopNotificationPermission = NotificationPermission | 'unsupported'

const preferenceKey = 'hermes.desktopNotifications.enabled'

function notificationApi() {
  if (typeof window === 'undefined' || !('Notification' in window)) return undefined
  return window.Notification
}

export function desktopNotificationsSupported() {
  return Boolean(notificationApi())
}

export function desktopNotificationPermission(): DesktopNotificationPermission {
  return notificationApi()?.permission ?? 'unsupported'
}

export function desktopNotificationsEnabled() {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(preferenceKey) === 'true'
}

export function setDesktopNotificationsEnabled(enabled: boolean) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(preferenceKey, enabled ? 'true' : 'false')
}

export async function requestDesktopNotificationPermission(): Promise<DesktopNotificationPermission> {
  const api = notificationApi()
  if (!api) return 'unsupported'

  const permission = await api.requestPermission()
  setDesktopNotificationsEnabled(permission === 'granted')
  return permission
}
