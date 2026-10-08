/**
 * Documentation assistant data layer.
 *
 * This module is the single seam between the UI and the backend. Today it
 * returns mock responses so the interface is fully interactive. To connect a
 * real RAG backend later, replace the body of `askDocumentationAssistant` with
 * a `fetch` to your API (see the commented example at the bottom). The UI only
 * depends on the exported types and the function signature, so nothing else
 * needs to change.
 */

import { ConversationNotFoundError } from '@/lib/history'

export type ChatRole = 'user' | 'assistant'

export type Source = {
  /** Human-readable title of the referenced document. */
  title: string
  /** Section or page reference within the document. */
  section: string
  /** Relevance score (0-1). Optional; used to sort/display confidence. */
  score?: number
  /** Optional deep link to the document. */
  url?: string
}

export type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  /** Sources are only present on assistant messages that cite documentation. */
  sources?: Source[]
  /** Browser preview URL of an image the user attached to this message. */
  imageUrl?: string
}

export type AssistantResponse = {
  content: string
  sources: Source[]
  /**
   * The saved conversation this answer was stored in. Only set when the person
   * is logged in; logged-out visitors get null (nothing is saved).
   */
  conversationId?: string | null
}

export const SUGGESTED_QUESTIONS = [
  'How do I configure Discovery for a new subnet?',
  'What causes the "MID Server down" alert?',
  'How do I set up Service Mapping for a business service?',
  'Explain event management alert correlation rules.',
] as const

const MOCK_ANSWERS: Array<{
  keywords: string[]
  response: AssistantResponse
}> = [
  {
    keywords: ['discovery', 'subnet', 'configure'],
    response: {
      content:
        'To configure Discovery for a new subnet, create a Discovery Schedule and point it at the subnet range. Assign a MID Server that can reach the target network, choose the "Networks" discovery type, and add the IP range under the schedule. Run the schedule on demand first to validate credentials and connectivity before enabling the recurring run.',
      sources: [
        {
          title: 'Discovery Administration Guide',
          section: 'Configure a Discovery Schedule',
          score: 0.94,
        },
        {
          title: 'MID Server Setup',
          section: 'Network reachability & credentials',
          score: 0.81,
        },
      ],
    },
  },
  {
    keywords: ['mid server', 'down', 'alert', 'offline'],
    response: {
      content:
        'A "MID Server down" alert usually means the MID Server has stopped sending heartbeats. Common causes are the MID Server service being stopped, expired or invalid credentials, or a network/firewall change blocking outbound HTTPS to your instance. Check the MID Server status record, review the agent logs (agent0.log), and confirm the service is running and can reach the instance URL.',
      sources: [
        {
          title: 'MID Server Troubleshooting',
          section: 'Heartbeat & connectivity failures',
          score: 0.91,
        },
        {
          title: 'Event Management Reference',
          section: 'MID Server health alerts',
          score: 0.76,
        },
      ],
    },
  },
  {
    keywords: ['service mapping', 'business service', 'map'],
    response: {
      content:
        'To set up Service Mapping for a business service, define an entry point (such as a URL or IP) and let top-down discovery trace the connected infrastructure. Start by creating the business service, add the entry point, then run discovery to build the map. Review and correct any unmapped connections using discovery patterns or manual connections.',
      sources: [
        {
          title: 'Service Mapping Guide',
          section: 'Create a business service map',
          score: 0.9,
        },
        {
          title: 'Discovery Patterns',
          section: 'Extending top-down discovery',
          score: 0.72,
        },
      ],
    },
  },
  {
    keywords: ['event', 'correlation', 'alert', 'rule'],
    response: {
      content:
        'Alert correlation in Event Management groups related events into a single actionable alert. Correlation rules can be based on CI relationships, time windows, or matching fields. Configure rules under Event Management > Alert Correlation, choose the correlation type, and set the time window so transient noise is grouped rather than paging your team repeatedly.',
      sources: [
        {
          title: 'Event Management Reference',
          section: 'Alert correlation rules',
          score: 0.88,
        },
        {
          title: 'ITOM Health Best Practices',
          section: 'Reducing alert noise',
          score: 0.7,
        },
      ],
    },
  },
]

const FALLBACK: AssistantResponse = {
  content:
    "Here's what I found based on the product documentation. For this topic, start by confirming the affected component and its current health state, then review the related configuration items and recent changes. If the issue persists, gather the relevant logs and check the troubleshooting guide for known error patterns.",
  sources: [
    {
      title: 'ITOM Getting Started',
      section: 'Troubleshooting overview',
      score: 0.68,
    },
  ],
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Ask the documentation assistant a question.
 *
 * Currently returns a mock response. Swap the implementation for a real
 * backend call without touching the UI.
 */


export async function askDocumentationAssistant(
  question: string,
  image?: File | null,
  conversationId?: string | null,
): Promise<AssistantResponse> {
  const API_URL = process.env.NEXT_PUBLIC_API_URL;

  if (!API_URL) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured");
  }

  let response: Response;

  // `credentials: "include"` sends the login cookie. Logged-in people get
  // their chat saved to history; without it the backend can't tell who is
  // asking and saves nothing. Logged-out visitors can still ask questions.
  if (image) {
    // With an image, use the multimodal endpoint (multipart form). The
    // backend analyzes the image and adds what it finds to the question.
    const form = new FormData();
    form.append("question", question);
    form.append("image", image);
    if (conversationId) {
      form.append("conversation_id", conversationId);
    }

    response = await fetch(`${API_URL}/ask/multimodal`, {
      method: "POST",
      credentials: "include",
      body: form,
    });
  } else {
    // No image: the JSON endpoint.
    response = await fetch(`${API_URL}/ask`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question,
        conversation_id: conversationId ?? null,
      }),
    });
  }

  // The saved conversation we were asked to continue no longer exists
  // (for example it was deleted in another tab).
  if (response.status === 404 && conversationId) {
    throw new ConversationNotFoundError();
  }

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  const data: { answer: string; conversation_id?: string | null } =
    await response.json();

  return {
    content: data.answer,
    sources: [],
    conversationId: data.conversation_id ?? null,
  };
}

  /**
   * Real backend example:
   *
   * const res = await fetch('/api/rag', {
   *   method: 'POST',
   *   headers: { 'Content-Type': 'application/json' },
   *   body: JSON.stringify({ question }),
   * })
   * if (!res.ok) throw new Error('Assistant request failed')
   * return (await res.json()) as AssistantResponse
   */