import { Bot } from 'lucide-react'

export function TypingIndicator() {
  return (
    <div className="flex gap-3 sm:gap-4" aria-live="polite">
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-violet text-white shadow-md shadow-primary/25">
        <Bot className="size-4" aria-hidden="true" />
      </span>
      <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-border/70 bg-card px-4 py-3.5">
        <span className="sr-only">Assistant is typing</span>
        <span className="typing-dot size-2 rounded-full bg-muted-foreground" />
        <span
          className="typing-dot size-2 rounded-full bg-muted-foreground"
          style={{ animationDelay: '0.15s' }}
        />
        <span
          className="typing-dot size-2 rounded-full bg-muted-foreground"
          style={{ animationDelay: '0.3s' }}
        />
      </div>
    </div>
  )
}
