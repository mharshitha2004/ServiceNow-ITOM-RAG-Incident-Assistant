'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { ArrowUp, Info, Lock, Paperclip } from 'lucide-react'
import {
  startIncidentChat,
  replyIncidentChat,
  IncidentThreadExpiredError,
  UnauthorizedError,
  type IncidentAwaiting,
} from '@/lib/incident-chat'
import {
  ConversationNotFoundError,
  getConversation,
  historyImageUrl,
  type StoredMessage,
} from '@/lib/history'
import type { ChatMessage as ChatMessageType } from '@/lib/assistant'
import { useAuth } from '@/lib/auth-context'
import {
  INCIDENT_ATTACHMENT_ACCEPT,
  useIncidentAttachment,
} from '@/lib/use-incident-attachment'
import { IncidentAttachmentPreview } from '@/components/incident-attachment-preview'
import { Button } from '@/components/ui/button'
import { ChatBackdrop } from '@/components/chat-backdrop'
import { ChatMessage } from '@/components/documentation/chat-message'
import { HistoryWorkspace } from '@/components/history/history-workspace'
import { TypingIndicator } from '@/components/documentation/typing-indicator'
import { ServerWaking } from '@/components/server-waking'
import { cn } from '@/lib/utils'

function createId() {
  return Math.random().toString(36).slice(2)
}

const WELCOME: ChatMessageType = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hi! Describe the issue you're seeing — I'll check the ServiceNow ITOM documentation first, and if it's not enough, I can create a real ServiceNow incident (P3/P4 only) on your behalf.",
}

// Shown when a saved incident flow was interrupted mid-step (server
// restart, memory-limit crash) and can be finished with "Retry".
const RETRY_NOTE =
  "The last step didn't finish because the server restarted. Press **Retry** to finish it. If the incident was already created in ServiceNow, you'll get the same incident number back, not a duplicate."

// Used when someone sends an attachment without typing anything.
const ATTACHMENT_ONLY_PROMPT =
  'Please look at the attached file and help me troubleshoot this issue.'

// A saved message from the backend -> the shape the chat UI renders. Saved
// screenshots are loaded from the backend (with the login cookie) rather than
// from a browser preview URL.
function toChatMessage(stored: StoredMessage): ChatMessageType {
  return {
    id: stored.id,
    role: stored.role,
    content: String(stored.content),
    imageUrl: stored.imageId ? historyImageUrl(stored.imageId) : undefined,
  }
}

export function IncidentAssistant() {
  const { user, isLoading: authLoading, isWaking } = useAuth()

  const [messages, setMessages] = useState<ChatMessageType[]>([WELCOME])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  // Server-side conversation state. `threadId === null` means the next
  // message starts a brand new incident flow.
  const [threadId, setThreadId] = useState<string | null>(null)
  const [awaiting, setAwaiting] = useState<IncidentAwaiting>(null)
  const [options, setOptions] = useState<string[] | null>(null)

  // Chat history: which saved conversation is open (null = a new chat that
  // hasn't been saved yet), and a counter that tells the sidebar to reload.
  // A conversation can hold several incident flows one after another; only
  // the latest one can be waiting for an answer (that's `threadId`).
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [openingConversation, setOpeningConversation] = useState(false)

  // Bumped whenever the person switches conversation or starts a new chat, so
  // a slow reply that arrives for the OLD conversation is ignored instead of
  // being shown in the new one.
  const epochRef = useRef(0)

  // Bumped on every send, so a background recovery (recoverPendingTurn)
  // never overwrites the thread of a message sent after it started.
  const sendSeqRef = useRef(0)

  // Pending attachment in the composer (picked, or pasted for images).
  // A screenshot, a .txt log file, or a .zip archive - see
  // lib/use-incident-attachment.ts for how each is handled server-side.
  const {
    file: attachmentFile,
    kind: attachmentKind,
    previewUrl,
    error: attachmentError,
    attach,
    clear: clearAttachment,
    handlePaste,
  } = useIncidentAttachment()

  // Object URLs for images already sent, revoked on unmount. The URL
  // itself lives on the message (imageUrl) so ChatMessage can show it.
  const sentImageUrlsRef = useRef<string[]>([])

  useEffect(() => {
    return () => {
      sentImageUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [])

  // Set only if a 401 arrives mid-conversation (the session cookie
  // expired or was cleared elsewhere) - distinct from the plain
  // "please log in" screen shown when there was never a session.
  const [sessionExpired, setSessionExpired] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, isLoading])

  function newChat() {
    epochRef.current += 1
    setConversationId(null)
    setMessages([WELCOME])
    setThreadId(null)
    setAwaiting(null)
    setOptions(null)
    setInput('')
    clearAttachment()
    setIsLoading(false)
    setOpeningConversation(false)
  }

  async function openConversation(id: string) {
    if (id === conversationId) return

    const epoch = ++epochRef.current

    setOpeningConversation(true)
    setIsLoading(false)
    setInput('')
    clearAttachment()

    try {
      const detail = await getConversation(id)
      if (epoch !== epochRef.current) return

      setConversationId(detail.id)
      setMessages([
        WELCOME,
        ...detail.messages.map(toChatMessage),
        ...(detail.pending?.awaiting === 'retry'
          ? [{ id: createId(), role: 'assistant' as const, content: RETRY_NOTE }]
          : []),
      ])

      // If the incident was paused waiting for an answer (and the backend
      // still has that thread), pick up exactly where it left off - the
      // quick-reply buttons come back too.
      setThreadId(detail.pending?.threadId ?? null)
      setAwaiting((detail.pending?.awaiting as IncidentAwaiting) ?? null)
      setOptions(detail.pending?.options ?? null)
    } catch (err) {
      if (epoch !== epochRef.current) return

      if (err instanceof ConversationNotFoundError) {
        // Deleted elsewhere. Drop it from the list and start fresh.
        setRefreshKey((k) => k + 1)
        newChat()
        return
      }

      setMessages((prev) => [
        ...prev,
        {
          id: createId(),
          role: 'assistant',
          content: "Sorry, I couldn't open that conversation. Please try again.",
        },
      ])
    } finally {
      if (epoch === epochRef.current) setOpeningConversation(false)
    }
  }

  async function send(text: string) {
    // Attachments can only go with the first message of an incident flow.
    const attached = threadId === null ? attachmentFile : null
    const attachedKind = threadId === null ? attachmentKind : null

    const trimmed = text.trim() || (attached ? ATTACHMENT_ONLY_PROMPT : '')
    if (!trimmed || isLoading || openingConversation) return

    const epoch = epochRef.current
    sendSeqRef.current += 1

    // Only an image gets shown as a thumbnail in the transcript - a
    // .txt/.zip is just named in the message text instead, since
    // there's nothing to preview.
    let imageUrl: string | undefined
    let displayContent = trimmed

    if (attached && attachedKind === 'image') {
      imageUrl = URL.createObjectURL(attached)
      sentImageUrlsRef.current.push(imageUrl)
    } else if (attached) {
      displayContent = `${trimmed}\n\n📎 Attached: ${attached.name}`
    }

    const userMessage: ChatMessageType = {
      id: createId(),
      role: 'user',
      content: displayContent,
      imageUrl,
    }

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    // Cleared here, not after the reply comes back - otherwise the
    // preview sits in the composer the whole time the request is in
    // flight, even though the message (and its attachment) was
    // already sent. `attached` above is a local snapshot, so clearing
    // the hook's state now doesn't change what's actually sent below.
    clearAttachment()
    setIsLoading(true)

    try {
      const turn =
        threadId === null
          ? await startIncidentChat(trimmed, attached, conversationId)
          : await replyIncidentChat(threadId, trimmed)

      if (epoch !== epochRef.current) return

      setThreadId(turn.done ? null : turn.threadId)
      setAwaiting(turn.done ? null : turn.awaiting)
      setOptions(turn.done ? null : turn.options)

      // Remember which saved conversation this belongs to, and refresh the
      // sidebar so it shows up (or moves to the top).
      if (turn.conversationId) setConversationId(turn.conversationId)
      setRefreshKey((k) => k + 1)

      setMessages((prev) => [
        ...prev,
        {
          id: createId(),
          role: 'assistant',
          content: turn.message,
        },
      ])
    } catch (err) {
      if (epoch !== epochRef.current) return

      if (err instanceof UnauthorizedError) {
        // The session expired mid-conversation. Stop the thread here
        // rather than pretending it can continue - the backend has
        // no valid caller to attach to a new incident until the
        // person logs back in.
        setThreadId(null)
        setAwaiting(null)
        setOptions(null)
        setSessionExpired(true)
        return
      }

      if (err instanceof IncidentThreadExpiredError) {
        // That incident flow can't be resumed any more. The person's next
        // message will start a new one in this same conversation.
        setThreadId(null)
        setAwaiting(null)
        setOptions(null)
        setMessages((prev) => [
          ...prev,
          {
            id: createId(),
            role: 'assistant',
            content:
              'That incident conversation is no longer active. Send your message again to start a new one.',
          },
        ])
        return
      }

      if (err instanceof ConversationNotFoundError) {
        setConversationId(null)
        setRefreshKey((k) => k + 1)
        setMessages((prev) => [
          ...prev,
          {
            id: createId(),
            role: 'assistant',
            content:
              'That saved conversation is no longer available. Send your message again to start a new one.',
          },
        ])
        return
      }

      // Any other failure (a 502 from the backend when the graph
      // crashed mid-turn, a network error, etc.) - reset thread state
      // here too, same as the two specific error types above. Leaving
      // threadId set to a now-broken thread meant the NEXT message
      // got sent as a reply to it instead of starting fresh - and
      // since the backend thread had already moved past its last
      // interrupt(), that reply had nothing left to consume it and
      // was silently discarded (see the P3/P4-mismatch bug this
      // fixes, together with the matching backend change in
      // /incident/reply that stops routing new replies to a thread
      // that crashed mid-turn in the first place).
      setThreadId(null)
      setAwaiting(null)
      setOptions(null)

      setMessages((prev) => [
        ...prev,
        {
          id: createId(),
          role: 'assistant',
          content:
            'Sorry, something went wrong reaching the assistant. Please try again.',
        },
      ])

      // If this was a reply in a saved conversation, ask the backend what
      // state the thread is really in. When the server died mid-step (the
      // usual cause - e.g. it restarted while creating the incident), it
      // now offers a "Retry" that finishes that step without creating a
      // duplicate. This does automatically what refreshing the page did.
      if (threadId !== null && conversationId) {
        void recoverPendingTurn(epoch, conversationId)
      }
    } finally {
      if (epoch === epochRef.current) setIsLoading(false)
    }
  }

  async function recoverPendingTurn(epoch: number, id: string) {
    const seq = sendSeqRef.current
    const stale = () => epoch !== epochRef.current || seq !== sendSeqRef.current

    // Give a restarting server a moment before asking.
    for (const delayMs of [1500, 5000, 15000]) {
      await new Promise((resolve) => setTimeout(resolve, delayMs))
      if (stale()) return

      try {
        const detail = await getConversation(id)
        if (stale()) return
        if (!detail.pending) return

        setThreadId(detail.pending.threadId)
        setAwaiting((detail.pending.awaiting as IncidentAwaiting) ?? null)
        setOptions(detail.pending.options ?? null)

        if (detail.pending.awaiting === 'retry') {
          setMessages((prev) => [
            ...prev,
            { id: createId(), role: 'assistant', content: RETRY_NOTE },
          ])
        }
        return
      } catch {
        // Server still restarting - try again after the next delay.
      }
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    void send(input)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (
      e.key === 'Enter' &&
      !e.shiftKey &&
      !e.nativeEvent.isComposing &&
      e.keyCode !== 229
    ) {
      e.preventDefault()
      void send(input)
    }
  }

  // Don't flash a "please log in" screen while we're still checking
  // for an existing session on first load.
  if (authLoading) {
    return isWaking ? <ServerWaking /> : null
  }

  if (!user || sessionExpired) {
    return (
      <div className="relative isolate flex h-[calc(100dvh-4rem)] items-center justify-center px-4">
        <ChatBackdrop />
        <div className="w-full max-w-sm rounded-2xl border border-border/70 bg-card/60 p-6 text-center">
          <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-primary/10">
            <Lock className="size-4 text-primary" />
          </div>
          <h2 className="mt-4 text-lg font-semibold text-foreground">
            {sessionExpired ? 'Your session expired' : 'Log in to continue'}
          </h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {sessionExpired
              ? 'Please log back in to keep working with the Incident Assistant.'
              : 'Incidents you create here are linked to your ServiceNow account, so you need to be logged in first.'}
          </p>
          <div className="mt-5 flex items-center justify-center gap-2">
            <Button
              nativeButton={false}
              render={<Link href="/login" />}
              className="bg-gradient-to-r from-primary to-violet text-primary-foreground hover:opacity-90"
            >
              Log in
            </Button>
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/register" />}
            >
              Sign up
            </Button>
          </div>
        </div>
      </div>
    )
  }

  const inConversation = threadId !== null
  const placeholder = inConversation
    ? options && options.length > 0
      ? `Reply, or pick an option below (${options.join(' / ')})`
      : 'Type your answer...'
    : 'Describe the issue, or give an image for troubleshooting'

  return (
    <HistoryWorkspace
      kind="incident"
      activeId={conversationId}
      refreshKey={refreshKey}
      onSelect={(id) => void openConversation(id)}
      onNewChat={newChat}
      onDeleted={(id) => {
        if (id === conversationId) newChat()
      }}
    >
      <div className="relative isolate flex h-full flex-col">
        <ChatBackdrop />
        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          <div
            className={cn(
              'mx-auto max-w-3xl space-y-6 px-4 py-8 transition-opacity sm:px-6',
              openingConversation && 'opacity-50',
            )}
          >
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            {(isLoading || openingConversation) && <TypingIndicator />}
          </div>
        </div>

        {/* Composer */}
        <div className="border-t border-border/60 bg-background/80 backdrop-blur">
          <div className="mx-auto max-w-3xl px-4 py-4 sm:px-6">
            {/* Quick-reply options for the current question, if any */}
            {options && options.length > 0 && !isLoading && !openingConversation && (
              <div className="mb-3 flex flex-wrap gap-2">
                {options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => void send(option)}
                    className="rounded-full border border-primary/30 bg-primary/10 px-3.5 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-primary/20"
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}

            {/* Pending attachment (only usable before a thread starts) */}
            {attachmentFile && attachmentKind && !inConversation && (
              <IncidentAttachmentPreview
                kind={attachmentKind}
                src={previewUrl}
                name={attachmentFile.name}
                onRemove={clearAttachment}
              />
            )}

            {attachmentError && (
              <p className="mb-3 text-xs text-red-400">{attachmentError}</p>
            )}

            <form onSubmit={handleSubmit}>
              <div className="flex items-end gap-2 rounded-2xl border border-border/70 bg-card/60 p-2 transition-colors focus-within:border-primary/50">
                <label htmlFor="incident-chat-input" className="sr-only">
                  Describe the issue or answer the assistant&apos;s question
                </label>

                {!inConversation && (
                  <>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept={INCIDENT_ATTACHMENT_ACCEPT}
                      className="hidden"
                      onChange={(e) => {
                        attach(e.target.files?.[0])
                        e.target.value = ''
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      title="Attach an image, .txt log file, or .zip archive for troubleshooting"
                      aria-label="Attach a file for troubleshooting"
                      className="flex size-9 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                    >
                      <Paperclip className="size-4" />
                    </button>
                  </>
                )}

                <textarea
                  id="incident-chat-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onPaste={inConversation ? undefined : handlePaste}
                  rows={1}
                  placeholder={placeholder}
                  className={cn(
                    'max-h-40 flex-1 resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground',
                  )}
                />

                <Button
                  type="submit"
                  size="icon"
                  disabled={
                    (!input.trim() && !attachmentFile) ||
                    isLoading ||
                    openingConversation
                  }
                  aria-label="Send message"
                  className="size-9 shrink-0 bg-gradient-to-br from-primary to-violet text-primary-foreground shadow-md shadow-primary/25 hover:opacity-90"
                >
                  <ArrowUp className="size-4" />
                </Button>
              </div>
              <p className="mt-2 text-center text-xs text-muted-foreground">
                Only P3 and P4 incidents can be created through this
                assistant. P1/P2 issues must go through the standard
                ServiceNow process.
              </p>
            </form>
          </div>
        </div>
      </div>
    </HistoryWorkspace>
  )
}