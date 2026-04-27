export default defineAppConfig({
  ui: {
    colors: {
      primary: 'blue',
      neutral: 'zinc'
    },
    chatMessage: {
      slots: {
        content: 'text-sm/6 font-normal'
      }
    },
    chatPrompt: {
      slots: {
        base: 'text-sm/5 font-normal'
      }
    },
    code: {
      base: 'inline rounded bg-muted px-1 py-0 font-mono text-xs/5 font-normal text-highlighted'
    },
    pre: {
      slots: {
        base: 'group overflow-x-auto whitespace-pre-wrap wrap-break-word rounded-md border border-muted bg-muted px-3 py-2 font-mono text-xs/5 font-normal focus:outline-none **:[.line]:block **:[.line.highlight]:-mx-3 **:[.line.highlight]:px-3 **:[.line.highlight]:bg-accented/50!'
      }
    }
  }
})
