const PREVIEWABLE_EXTENSIONS = new Set([
  'bash',
  'c',
  'conf',
  'cpp',
  'cs',
  'css',
  'csv',
  'dart',
  'env',
  'go',
  'graphql',
  'h',
  'html',
  'ini',
  'java',
  'js',
  'json',
  'jsx',
  'kt',
  'log',
  'lua',
  'md',
  'mjs',
  'php',
  'plist',
  'py',
  'rb',
  'rs',
  'scss',
  'sh',
  'sql',
  'swift',
  'toml',
  'ts',
  'tsx',
  'txt',
  'vue',
  'xml',
  'yaml',
  'yml',
  'zsh'
])

export const LOCAL_PATH_PATTERN = /(?:^|[\s("'`[{])((?:\.?\.?\/|[\w@.-]+\/|\/)[^\s`'"<>]+)(?=[.,:;!?)]?["'`)}\]]?(?:\s|$))/g

export function normalizePreviewPathCandidate(value: string) {
  let candidate = value.trim()
  candidate = stripTrailingPunctuation(candidate)
  candidate = stripMatchingWrapper(candidate, '`')
  candidate = stripMatchingWrapper(candidate, '"')
  candidate = stripMatchingWrapper(candidate, "'")
  candidate = stripTrailingPunctuation(candidate)
  return candidate
}

export function isPreviewablePathCandidate(value: string) {
  const candidate = normalizePreviewPathCandidate(value)
  if (!candidate || candidate.includes('\n')) return false
  if (/^(?:https?|file):\/\//i.test(candidate)) return false
  if (/\s/.test(candidate)) return false

  if (isPathLike(candidate)) return true

  const extension = extensionFor(candidate)
  return extension ? PREVIEWABLE_EXTENSIONS.has(extension) : false
}

function isPathLike(value: string) {
  const extension = extensionFor(value)
  const slashCount = countSlashes(value)

  return value.startsWith('./')
    || value.startsWith('../')
    || /^\.[^/]+\//.test(value)
    || (value.startsWith('/') && (Boolean(extension) || slashCount >= 3))
    || (!value.startsWith('/') && value.includes('/') && (Boolean(extension) || slashCount >= 2))
}

function countSlashes(value: string) {
  return (value.match(/\//g) || []).length
}

function stripMatchingWrapper(value: string, wrapper: string) {
  return value.startsWith(wrapper) && value.endsWith(wrapper) && value.length >= 2
    ? value.slice(1, -1).trim()
    : value
}

function stripTrailingPunctuation(value: string) {
  return value.replace(/[.,:;!?\])}]+$/, '')
}

function extensionFor(filename: string) {
  const index = filename.lastIndexOf('.')
  if (index <= 0 || index === filename.length - 1) return null
  return filename.slice(index + 1).toLowerCase()
}
