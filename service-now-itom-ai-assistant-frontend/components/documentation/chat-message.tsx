import { Bot, FileText, User } from 'lucide-react'
import type { ChatMessage as ChatMessageType } from '@/lib/assistant'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === 'user'

  return (
    <div
      className={cn(
        'flex gap-3 sm:gap-4',
        isUser ? 'flex-row-reverse' : 'flex-row',
      )}
    >
      {/* Avatar */}
      <span
        className={cn(
          'mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg',
          isUser
            ? 'bg-secondary text-foreground'
            : 'bg-gradient-to-br from-primary to-violet text-white shadow-md shadow-primary/25',
        )}
        aria-hidden="true"
      >
        {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
      </span>

      <div className={cn('flex max-w-[85%] flex-col gap-2', isUser && 'items-end')}>
        <span className="sr-only">
          {isUser ? 'You said' : 'ITOM Assistant replied'}:
        </span>

        {/* Image the user attached to this message */}
        {message.imageUrl && (
          <>
            {/* Blob URL from the browser, so next/image can't optimize it. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={message.imageUrl}
              alt="Image you attached"
              className="max-h-64 max-w-[16rem] rounded-2xl border border-border/70 object-cover"
            />
          </>
        )}
        <div className={cn('flex max-w-[90%] flex-col gap-2', isUser && 'items-end')}/>
        <div
          className={cn(
            'rounded-2xl px-5 py-4 text-sm leading-relaxed',
            isUser
              ? 'rounded-tr-sm border border-cyan-400/20 bg-gradient-to-br from-teal-700 to-cyan-800 text-white shadow-md shadow-black/20'
              : 'rounded-tl-sm border border-border/70 bg-card text-card-foreground',
          )}
        >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => (
              <h1 className="mb-2 mt-3 text-base font-bold">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="mb-2 mt-3 text-[15px] font-bold">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="mb-1.5 mt-3 text-sm font-bold">
                {children}
              </h3>
            ),
            p: ({ children }) => (
              <p className="mb-2.5 leading-6 last:mb-0">
                {children}
              </p>
            ),
            ul: ({ children }) => (
              <ul
                style={{
                  display: 'block',
                  listStyleType: 'disc',
                  paddingLeft: '32px',
                  margin: '12px 0',
                }}
              >
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol
                style={{
                  listStyleType: 'decimal',
                  paddingLeft: '1.25rem',
                  marginBottom: '0.75rem',
                }}
              >
                {children}
              </ol>
            ),
            li: ({ children }) => (
              <li className="flex items-start gap-2">
                <span className="shrink-0 font-bold">•</span>
                <div className="min-w-0 flex-1">
                  {children}
                </div>
              </li>
            ),

            strong: ({ children }) => (
              <strong className="font-bold">
                {children}
              </strong>
            ),
            code: ({ children }) => (
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs text-foreground">
                {children}
              </code>
            ),
          }}
        >
          {message.content}
        </ReactMarkdown>
        </div>

        {/* Source citations */}
        {message.sources && message.sources.length > 0 && (
          <div className="w-full rounded-xl border border-border/60 bg-secondary/40 p-3">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <FileText className="size-3.5" aria-hidden="true" />
              Sources
            </p>
            <ul className="space-y-1.5">
              {message.sources.map((source, i) => (
                <li
                  key={`${source.title}-${i}`}
                  className="flex items-start justify-between gap-3 text-xs"
                >
                  <span className="text-foreground">
                    <span className="font-medium">{source.title}</span>
                    <span className="text-muted-foreground">
                      {' '}
                      &mdash; {source.section}
                    </span>
                  </span>
                  {typeof source.score === 'number' && (
                    <span className="shrink-0 rounded-full bg-primary/15 px-2 py-0.5 font-medium text-primary">
                      {Math.round(source.score * 100)}%
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}