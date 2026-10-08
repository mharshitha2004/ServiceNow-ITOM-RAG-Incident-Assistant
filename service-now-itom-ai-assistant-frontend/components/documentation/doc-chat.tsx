'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Paperclip, Sparkles } from 'lucide-react'
import {
  askDocumentationAssistant,
  SUGGESTED_QUESTIONS,
  type ChatMessage as ChatMessageType,
} from '@/lib/assistant'
import {
  ConversationNotFoundError,
  getConversation,
  historyImageUrl,
  type StoredMessage,
} from '@/lib/history'
import { Button } from '@/components/ui/button'
import { ChatBackdrop } from '@/components/chat-backdrop'
import { ChatMessage } from '@/components/documentation/chat-message'
import { HistoryWorkspace } from '@/components/history/history-workspace'
import { ImageAttachmentPreview } from '@/components/image-attachment-preview'
import { useImageAttachment } from '@/lib/use-image-attachment'
import { TypingIndicator } from '@/components/documentation/typing-indicator'
import { cn } from '@/lib/utils'

function createId() {
  return Math.random().toString(36).slice(2)
}

const WELCOME: ChatMessageType = {
  id: 'welcome',
  role: 'assistant',
  content:
    "Hi! I'm your documentation assistant. Ask me anything about ServiceNow ITOM — Discovery, MID Servers, CMDB, Service Mapping, or Event Management — and I'll answer using the product docs, Community articles with citations.",
}

// Used when someone sends a screenshot without typing anything.
const IMAGE_ONLY_PROMPT =
  'Please analyze the attached screenshot and help me understand and resolve it.'

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

export function DocChat() {
  const [messages, setMessages] = useState<ChatMessageType[]>([WELCOME])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  // Chat history: which saved conversation is open (null = a new chat that
  // hasn't been saved yet), and a counter that tells the sidebar to reload.
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [openingConversation, setOpeningConversation] = useState(false)

  // Bumped whenever the person switches conversation or starts a new chat, so
  // a slow reply that arrives for the OLD conversation is ignored instead of
  // being shown in the new one.
  const epochRef = useRef(0)

  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Pending attachment in the composer (picked or pasted).
  const {
    file: imageFile,
    previewUrl,
    error: imageError,
    attach,
    clear: clearImage,
    handlePaste,
  } = useImageAttachment()

  // Object URLs for images already sent, revoked on unmount. The URL
  // itself lives on the message (imageUrl) so ChatMessage can show it.
  const sentImageUrlsRef = useRef<string[]>([])

  useEffect(() => {
    return () => {
      sentImageUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [])

  // Keep the newest message in view.
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
    setInput('')
    clearImage()
    setIsLoading(false)
    setOpeningConversation(false)
  }

  async function openConversation(id: string) {
    if (id === conversationId) return

    const epoch = ++epochRef.current

    setOpeningConversation(true)
    setIsLoading(false)
    setInput('')
    clearImage()

    try {
      const detail = await getConversation(id)
      if (epoch !== epochRef.current) return

      setConversationId(detail.id)
      setMessages([WELCOME, ...detail.messages.map(toChatMessage)])
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

  // `withImage` is false for the suggested-question buttons, so clicking one
  // doesn't swallow a screenshot that's still waiting in the composer.
  async function send(question: string, withImage = true) {
    const attachedImage = withImage ? imageFile : null

    const trimmed = question.trim() || (attachedImage ? IMAGE_ONLY_PROMPT : '')
    if (!trimmed || isLoading || openingConversation) return

    const epoch = epochRef.current

    let imageUrl: string | undefined
    if (attachedImage) {
      imageUrl = URL.createObjectURL(attachedImage)
      sentImageUrlsRef.current.push(imageUrl)
    }

    const userMessage: ChatMessageType = {
      id: createId(),
      role: 'user',
      content: trimmed,
      imageUrl,
    }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    if (attachedImage) clearImage()
    setIsLoading(true)

    try {
      const response = await askDocumentationAssistant(
        trimmed,
        attachedImage,
        conversationId,
      )
      if (epoch !== epochRef.current) return

      // Logged-in people get a conversation id back: remember it so the next
      // question continues the same conversation, and refresh the sidebar.
      if (response.conversationId) {
        setConversationId(response.conversationId)
        setRefreshKey((k) => k + 1)
      }

      setMessages((prev) => [
        ...prev,
        {
          id: createId(),
          role: 'assistant',
          content: response.content,
          sources: response.sources,
        },
      ])
    } catch (err) {
      if (epoch !== epochRef.current) return

      if (err instanceof ConversationNotFoundError) {
        setConversationId(null)
        setRefreshKey((k) => k + 1)
        setMessages((prev) => [
          ...prev,
          {
            id: createId(),
            role: 'assistant',
            content:
              'That saved conversation is no longer available. Please send your question again to start a new one.',
          },
        ])
        return
      }

      setMessages((prev) => [
        ...prev,
        {
          id: createId(),
          role: 'assistant',
          content:
            'Sorry, something went wrong while fetching an answer. Please try again.',
        },
      ])
    } finally {
      if (epoch === epochRef.current) setIsLoading(false)
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    void send(input)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Submit on Enter, but respect IME composition and Shift+Enter for newlines.
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

  const showSuggestions =
    messages.length === 1 && !isLoading && !openingConversation

  return (
    <HistoryWorkspace
      kind="documentation"
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

            {showSuggestions && (
              <div className="pt-2">
                <p className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <Sparkles
                    className="size-3.5 text-primary"
                    aria-hidden="true"
                  />
                  Suggested questions
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {SUGGESTED_QUESTIONS.map((question) => (
                    <button
                      key={question}
                      type="button"
                      onClick={() => void send(question, false)}
                      className="rounded-xl border border-border/70 bg-card/60 px-4 py-3 text-left text-sm text-muted-foreground transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Composer */}
        <div className="border-t border-border/60 bg-background/80 backdrop-blur">
          <form
            onSubmit={handleSubmit}
            className="mx-auto max-w-3xl px-4 py-4 sm:px-6"
          >
            {previewUrl && (
              <ImageAttachmentPreview
                src={previewUrl}
                name={imageFile?.name}
                onRemove={clearImage}
              />
            )}

            {imageError && (
              <p className="mb-3 text-xs text-red-400">{imageError}</p>
            )}

            <div className="flex items-end gap-2 rounded-2xl border border-border/70 bg-card/60 p-2 transition-colors focus-within:border-primary/50">
              <label htmlFor="chat-input" className="sr-only">
                Ask a question about the product documentation
              </label>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                className="hidden"
                onChange={(e) => {
                  attach(e.target.files?.[0])
                  e.target.value = ''
                }}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                title="Attach or paste a screenshot or error image"
                aria-label="Attach an image"
                className="flex size-9 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <Paperclip className="size-4" />
              </button>
              <textarea
                id="chat-input"
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
                rows={1}
                placeholder="Ask anything about ServiceNow ITOM, or attach an image for troubleshooting"
                className="max-h-40 flex-1 resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground"
              />
              <Button
                type="submit"
                size="icon"
                disabled={
                  (!input.trim() && !imageFile) ||
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
              Responses are generated from product documentation. Verify
              critical steps before acting.
            </p>
          </form>
        </div>
      </div>
    </HistoryWorkspace>
  )
}