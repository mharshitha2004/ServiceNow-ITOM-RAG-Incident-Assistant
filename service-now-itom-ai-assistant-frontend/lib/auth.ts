/**
 * Auth API client.
 *
 * Sessions are a JWT in an httpOnly cookie set by the backend, so every
 * call here uses `credentials: 'include'` to send/receive it - there is
 * no token for this code to read or store itself.
 */

export type User = {
  id: string
  email: string
  servicenowUsername: string
  /** Display name, resolved from the linked ServiceNow user. Drives the
   * avatar's initials until/unless a photo is uploaded. */
  name: string
  hasAvatar: boolean
}

export class UnauthorizedError extends Error {
  constructor(message = 'Not authenticated') {
    super(message)
    this.name = 'UnauthorizedError'
  }
}

function apiUrl(): string {
  const API_URL = process.env.NEXT_PUBLIC_API_URL

  if (!API_URL) {
    throw new Error('NEXT_PUBLIC_API_URL is not configured')
  }

  return API_URL
}

/**
 * Base URL for the current user's avatar photo. Only meaningful when
 * `hasAvatar` is true - append a cache-busting query param after any
 * upload/removal, since the URL itself never changes.
 */
export function avatarUrl(): string {
  return `${apiUrl()}/auth/avatar`
}

function shapeUser(data: {
  id: string
  email: string
  servicenow_username: string
  name: string
  has_avatar: boolean
}): User {
  return {
    id: data.id,
    email: data.email,
    servicenowUsername: data.servicenow_username,
    name: data.name,
    hasAvatar: data.has_avatar,
  }
}

async function handleResponse(response: Response): Promise<any> {
  if (response.status === 401) {
    throw new UnauthorizedError()
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(data?.detail || `Request failed: ${response.status}`)
  }

  return response.json()
}

/**
 * Register a new account. The ServiceNow username is validated against
 * the PDI server-side - a rejected request usually means that username
 * doesn't exist on ServiceNow.
 */
export async function register(
  email: string,
  password: string,
  servicenowUsername: string,
  name: string,
): Promise<User> {
  const response = await fetch(`${apiUrl()}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      email,
      password,
      servicenow_username: servicenowUsername,
      name,
    }),
  })

  return shapeUser(await handleResponse(response))
}

export async function login(email: string, password: string): Promise<User> {
  const response = await fetch(`${apiUrl()}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email, password }),
  })

  return shapeUser(await handleResponse(response))
}

export async function logout(): Promise<void> {
  await fetch(`${apiUrl()}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
}

/**
 * Returns the logged-in user, or null if there's no active session.
 * Used on app load to restore auth state from the session cookie.
 */
export async function getCurrentUser(): Promise<User | null> {
  const response = await fetch(`${apiUrl()}/auth/me`, {
    credentials: 'include',
  })

  if (response.status === 401) {
    return null
  }

  return shapeUser(await handleResponse(response))
}

/**
 * Update the account's email and/or linked ServiceNow username. Pass only
 * the field(s) you want to change - a changed ServiceNow username is
 * re-validated against the PDI server-side, same as at registration, and
 * a rejected value leaves the account unchanged.
 */
export async function updateProfile(fields: {
  email?: string
  servicenowUsername?: string
  name?: string
}): Promise<User> {
  const response = await fetch(`${apiUrl()}/auth/profile`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      email: fields.email,
      servicenow_username: fields.servicenowUsername,
      name: fields.name,
    }),
  })

  return shapeUser(await handleResponse(response))
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const response = await fetch(`${apiUrl()}/auth/password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })

  await handleResponse(response)
}

export async function uploadAvatar(file: File): Promise<User> {
  const form = new FormData()
  form.append('image', file)

  const response = await fetch(`${apiUrl()}/auth/avatar`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  })

  return shapeUser(await handleResponse(response))
}

export async function removeAvatar(): Promise<User> {
  const response = await fetch(`${apiUrl()}/auth/avatar`, {
    method: 'DELETE',
    credentials: 'include',
  })

  return shapeUser(await handleResponse(response))
}