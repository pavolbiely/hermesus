import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  detectReadAloudLanguage,
  edgeReadAloudVoice,
  readAloudLanguageLocale
} from '../shared/readAloud/language.ts'

test('detects Slovak read-aloud language and Edge voice', () => {
  const language = detectReadAloudLanguage('ďakujem, toto je odpoveď v slovenčine a má rešpektovať nastavenie')

  assert.equal(language, 'sk')
  assert.equal(readAloudLanguageLocale(language), 'sk-SK')
  assert.equal(edgeReadAloudVoice(language), 'sk-SK-LukasNeural')
})

test('detects Czech separately from Slovak', () => {
  assert.equal(detectReadAloudLanguage('děkuji, odpověď má používat správný jazyk'), 'cs')
})

test('falls back to English for unrecognized text', () => {
  assert.equal(detectReadAloudLanguage('Plain response with no strong language hints.'), 'en')
})
