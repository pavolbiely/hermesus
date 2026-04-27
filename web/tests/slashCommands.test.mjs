import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  exactSlashCommandMatch,
  filterSlashCommands,
  nextSlashCommandDismissedState
} from '../app/utils/slashCommands.ts'

const commands = [
  { id: 'help', name: '/help', description: 'Show commands', requiresWorkspace: false },
  { id: 'status', name: '/status', description: 'Show status', requiresWorkspace: false },
  { id: 'changes', name: '/changes', description: 'Show workspace changes', requiresWorkspace: true }
]

test('only exact known slash commands are recognized for autocomplete matching', () => {
  assert.equal(exactSlashCommandMatch(commands, '/help')?.name, '/help')
  assert.equal(exactSlashCommandMatch(commands, '/help   ')?.name, '/help')
  assert.equal(exactSlashCommandMatch(commands, '/help now'), null)
  assert.equal(exactSlashCommandMatch(commands, '/unknown'), null)
  assert.equal(exactSlashCommandMatch(commands, 'please /help'), null)
})

test('slash command autocomplete includes all known commands for leading slash', () => {
  assert.deepEqual(filterSlashCommands(commands, '/').map(command => command.name), [
    '/help',
    '/status',
    '/changes'
  ])
  assert.deepEqual(filterSlashCommands(commands, '/st').map(command => command.name), ['/status'])
  assert.deepEqual(filterSlashCommands(commands, 'hello /').map(command => command.name), [])
})

test('exact slash commands remain plain input after autocomplete selection', () => {
  assert.equal(exactSlashCommandMatch(commands, '/help')?.name, '/help')
  assert.equal(filterSlashCommands(commands, '/he')[0]?.name, '/help')
})

test('escape dismissal stays closed until leaving slash command input', () => {
  assert.equal(nextSlashCommandDismissedState('', '/', false), false)
  assert.equal(nextSlashCommandDismissedState('/', '/h', true), true)
  assert.equal(nextSlashCommandDismissedState('/h', '/help', true), true)
  assert.equal(nextSlashCommandDismissedState('/help', '/help now', true), false)
  assert.equal(nextSlashCommandDismissedState('/help now', '/', false), false)
})
