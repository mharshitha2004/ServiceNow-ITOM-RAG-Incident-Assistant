/**
 * Incident assistant data layer.
 *
 * This is the real integration: every call goes to the FastAPI backend,
 * which drives the LangGraph agent (RAG-first troubleshooting, then an
 * optional MCP-backed ServiceNow incident creation).
 *
 * The conversation is turn-based and stateful on the server:
 *  - `startIncidentChat` begins a new thread and returns a `threadId`.
 *  - `replyIncidentChat` sends the next answer for that same thread.
 * Each turn comes back either paused (`done: false`, with `awaiting` /
 * `options` describing what kind of answer is expected next) or finished
 * (`done: true`, `message` is the final answer).
 *
 * Both endpoints require a logged-in session (so the incident gets the
 * right ServiceNow caller), so every request sends the session cookie
 * via `credentials: 'include'` and a 401 surfaces as `UnauthorizedError`
 * so the UI can prompt the person to log in again.
 */

import { ConversationNotFoundError } from '@/lib/history'

export type IncidentAwaiting =
  | 'satisfaction'
  | 'confirm_incident'
  | 'priority'
  // The server died partway through the last step (e.g. while creating
  // the incident). The only option is "Retry", which re-runs that step -
  // safe, because incident creation can't create a duplicate.
  | 'retry'
  | null

export type IncidentTurn = {
  threadId: string
  done: boolean
  message: string
  awaiting: IncidentAwaiting
  options: string[] | null
  /** The saved conversation (chat history entry) this turn belongs to. */
  conversationId: string | null
}

export class UnauthorizedError extends Error {
  constructor(message = 'Not authenticated') {
    super(message)
    this.name = 'UnauthorizedError'
  }
}

/**
 * The incident thread being replied to is no longer waiting for an answer
 * (it finished, or its saved state is gone). The person needs to start a
 * fresh incident conversation.
 */
export class IncidentThreadExpiredError extends Error {
  constructor(message = 'This incident conversation is no longer active') {
    super(message)
    this.name = 'IncidentThreadExpiredError'
  }
}

function apiUrl(): string {
  const API_URL = process.env.NEXT_PUBLIC_API_URL

  if (!API_URL) {
    throw new Error('NEXT_PUBLIC_API_URL is not configured')
  }

  return API_URL
}

function shapeTurn(data: {
  thread_id: string
  done: boolean
  message: string
  awaiting?: IncidentAwaiting
  options?: string[] | null
  conversation_id?: string | null
}): IncidentTurn {
  return {
    threadId: data.thread_id,
    done: data.done,
    message: data.message,
    awaiting: data.awaiting ?? null,
    options: data.options ?? null,
    conversationId: data.conversation_id ?? null,
  }
}

async function shapeResponse(response: Response): Promise<IncidentTurn> {
  if (response.status === 401) {
    throw new UnauthorizedError()
  }

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`)
  }

  return shapeTurn(await response.json())
}

/**
 * Start a new incident conversation. Optionally attach a screenshot /
 * error image — the backend will run it through the multimodal analysis
 * step before checking documentation.
 */
export async function startIncidentChat(
  question: string,
  image?: File | null,
  conversationId?: string | null,
): Promise<IncidentTurn> {
  const form = new FormData()
  form.append('question', question)
  if (image) {
    form.append('image', image)
  }
  // Add this incident to an existing saved conversation instead of
  // creating a new history entry.
  if (conversationId) {
    form.append('conversation_id', conversationId)
  }

  const response = await fetch(`${apiUrl()}/incident/start`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  })

  if (response.status === 404 && conversationId) {
    throw new ConversationNotFoundError()
  }

  return shapeResponse(response)
}

/**
 * Continue an existing incident conversation with the user's next answer
 * (free text, or one of the suggested `options` from the previous turn).
 */
export async function replyIncidentChat(
  threadId: string,
  answer: string,
): Promise<IncidentTurn> {
  const response = await fetch(`${apiUrl()}/incident/reply`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, answer }),
  })

  if (response.status === 404) {
    throw new IncidentThreadExpiredError()
  }

  return shapeResponse(response)
}