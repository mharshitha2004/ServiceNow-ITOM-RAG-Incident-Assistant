/**
 * Chat history API client.
 *
 * Talks to the backend's /conversations and /images endpoints. Like the
 * rest of the auth-protected API, every call sends the session cookie via
 * `credentials: 'include'`.
 */

export type ConversationKind = 'documentation' | 'incident'

export type ConversationSummary = {
  id: string
  kind: ConversationKind
  title: string
  /** ISO timestamp (UTC). */
  updatedAt: string
}

export type StoredMessage = {
  id: string
  role: 'user' | 'assistant'
  /**
   * Exactly what the backend returned for this turn. For documentation
   * answers that's the raw answer, so it needs the same processing as a
   * live answer before it's displayed.
   */
  content: string
  imageId: string | null
  /** Incident questions only: what kind of answer was being asked for. */
  awaiting: string | null
  options: string[] | null
  createdAt: string
}

/** An incident thread that is still waiting for the person's answer. */
export type PendingTurn = {
  threadId: string
  awaiting: string | null
  options: string[] | null
}

export type ConversationDetail = {
  id: string
  kind: ConversationKind
  title: string
  messages: StoredMessage[]
  pending: PendingTurn | null
}

export class ConversationNotFoundError extends Error {
  constructor() {
    super('Conversation not found.')
    this.name = 'ConversationNotFoundError'
  }
}

function apiUrl(): string {
  const API_URL = process.env.NEXT_PUBLIC_API_URL

  if (!API_URL) {
    throw new Error('NEXT_PUBLIC_API_URL is not configured')
  }

  return API_URL
}

/** URL to load a saved screenshot in an <img>. Needs the session cookie. */
export function historyImageUrl(imageId: string): string {
  return `${apiUrl()}/images/${encodeURIComponent(imageId)}`
}

export async function listConversations(
  kind: ConversationKind,
): Promise<ConversationSummary[]> {
  const response = await fetch(
    `${apiUrl()}/conversations?kind=${encodeURIComponent(kind)}`,
    { credentials: 'include' },
  )

  // Logged out (or session expired): there's simply no history to show.
  if (response.status === 401) return []

  if (!response.ok) {
    throw new Error(`Failed to load history: ${response.status}`)
  }

  const data: {
    id: string
    kind: ConversationKind
    title: string
    updated_at: string
  }[] = await response.json()

  return data.map((item) => ({
    id: item.id,
    kind: item.kind,
    title: item.title,
    updatedAt: item.updated_at,
  }))
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const response = await fetch(
    `${apiUrl()}/conversations/${encodeURIComponent(id)}`,
    { credentials: 'include' },
  )

  if (response.status === 404) throw new ConversationNotFoundError()

  if (!response.ok) {
    throw new Error(`Failed to load conversation: ${response.status}`)
  }

  const data: {
    id: string
    kind: ConversationKind
    title: string
    messages: {
      id: string
      role: 'user' | 'assistant'
      content: string
      image_id: string | null
      awaiting: string | null
      options: string[] | null
      created_at: string
    }[]
    pending: {
      thread_id: string
      awaiting: string | null
      options: string[] | null
    } | null
  } = await response.json()

  return {
    id: data.id,
    kind: data.kind,
    title: data.title,
    messages: data.messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      imageId: m.image_id,
      awaiting: m.awaiting,
      options: m.options,
      createdAt: m.created_at,
    })),
    pending: data.pending
      ? {
          threadId: data.pending.thread_id,
          awaiting: data.pending.awaiting,
          options: data.pending.options,
        }
      : null,
  }
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await fetch(
    `${apiUrl()}/conversations/${encodeURIComponent(id)}`,
    { method: 'DELETE', credentials: 'include' },
  )

  if (!response.ok && response.status !== 404) {
    throw new Error(`Failed to delete conversation: ${response.status}`)
  }
}