import { getHighlighter, highlightCodeBlocks } from '@comark/nuxt/plugins/highlight'
import type { LanguageRegistration } from 'shiki'

type LanguageImport = () => Promise<{ default: LanguageRegistration | LanguageRegistration[] }>
type MarkdownHighlightState = { tree: { nodes: unknown[] } }

const languageImports: Record<string, LanguageImport> = {
  c: () => import('shiki/dist/langs/c.mjs'),
  cpp: () => import('shiki/dist/langs/cpp.mjs'),
  csharp: () => import('shiki/dist/langs/csharp.mjs'),
  css: () => import('shiki/dist/langs/css.mjs'),
  csv: () => import('shiki/dist/langs/csv.mjs'),
  dart: () => import('shiki/dist/langs/dart.mjs'),
  dockerfile: () => import('shiki/dist/langs/dockerfile.mjs'),
  dotenv: () => import('shiki/dist/langs/dotenv.mjs'),
  go: () => import('shiki/dist/langs/go.mjs'),
  graphql: () => import('shiki/dist/langs/graphql.mjs'),
  html: () => import('shiki/dist/langs/html.mjs'),
  ini: () => import('shiki/dist/langs/ini.mjs'),
  java: () => import('shiki/dist/langs/java.mjs'),
  jsx: () => import('shiki/dist/langs/jsx.mjs'),
  kotlin: () => import('shiki/dist/langs/kotlin.mjs'),
  lua: () => import('shiki/dist/langs/lua.mjs'),
  makefile: () => import('shiki/dist/langs/makefile.mjs'),
  php: () => import('shiki/dist/langs/php.mjs'),
  python: () => import('shiki/dist/langs/python.mjs'),
  ruby: () => import('shiki/dist/langs/ruby.mjs'),
  rust: () => import('shiki/dist/langs/rust.mjs'),
  scss: () => import('shiki/dist/langs/scss.mjs'),
  sql: () => import('shiki/dist/langs/sql.mjs'),
  swift: () => import('shiki/dist/langs/swift.mjs'),
  toml: () => import('shiki/dist/langs/toml.mjs'),
  vue: () => import('shiki/dist/langs/vue.mjs'),
  xml: () => import('shiki/dist/langs/xml.mjs')
}

const languageAliases: Record<string, string> = {
  cs: 'csharp',
  h: 'c',
  md: 'markdown',
  mjs: 'javascript',
  rb: 'ruby',
  rs: 'rust',
  sh: 'bash',
  yml: 'yaml'
}
const languageCache = new Map<string, Promise<LanguageRegistration | LanguageRegistration[] | null>>()

export function createMarkdownHighlightPlugin() {
  return {
    name: 'markdown-highlight',
    async post(state: MarkdownHighlightState) {
      const languages = await loadLanguages(findCodeBlockLanguages(state.tree.nodes))
      await ensureHighlighterLanguages(languages)
      state.tree = await highlightCodeBlocks(state.tree as Parameters<typeof highlightCodeBlocks>[0], { languages })
    }
  }
}

async function ensureHighlighterLanguages(languages: Array<LanguageRegistration | LanguageRegistration[] | null>) {
  const resolvedLanguages = languages.filter(language => language !== null)
  if (!resolvedLanguages.length) return

  // Comark's singleton highlighter can be created by a concurrent render without
  // the language set from this render. A second pass ensures the resolved
  // languages are loaded after any in-flight highlighter initialization settles.
  await getHighlighter({ languages: resolvedLanguages })
  await getHighlighter({ languages: resolvedLanguages })
}

function findCodeBlockLanguages(nodes: unknown[]) {
  const languages = new Set<string>()
  visitNodes(nodes, node => {
    if (!Array.isArray(node) || node[0] !== 'pre') return
    const language = typeof node[1]?.language === 'string' ? normalizeLanguage(node[1].language) : null
    if (language) languages.add(language)
  })
  return languages
}

function visitNodes(nodes: unknown[], visitor: (node: unknown) => void) {
  for (const node of nodes) {
    visitor(node)
    if (Array.isArray(node)) visitNodes(node.slice(2), visitor)
  }
}

async function loadLanguages(languageNames: Set<string>) {
  const loaded = await Promise.all(Array.from(languageNames, loadLanguage))
  return loaded.filter(language => language !== null)
}

function loadLanguage(language: string) {
  if (!languageCache.has(language)) {
    languageCache.set(language, importLanguage(language))
  }
  return languageCache.get(language)!
}

async function importLanguage(language: string) {
  const importer = languageImports[language]
  if (!importer) return null

  try {
    return (await importer()).default
  } catch (error) {
    console.warn(`Could not load syntax highlighter for ${language}`, error)
    return null
  }
}

function normalizeLanguage(language: string) {
  const value = language.trim().toLowerCase()
  return languageAliases[value] || value
}
