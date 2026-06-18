import { useState, useCallback } from 'react'

const storageKey = (roomId) => `dp_auth_${roomId}`

/**
 * Auth state for a specific room, backed by localStorage.
 * auth shape: { token, role: 'seller'|'buyer', name, expires_at (unix) }
 */
export function useAuth(roomId) {
  const [auth, setAuthState] = useState(() => {
    if (!roomId) return null
    try {
      const raw = localStorage.getItem(storageKey(roomId))
      if (!raw) return null
      const parsed = JSON.parse(raw)
      if (parsed.expires_at && Math.floor(Date.now() / 1000) > parsed.expires_at) {
        localStorage.removeItem(storageKey(roomId))
        return null
      }
      return parsed
    } catch {
      return null
    }
  })

  const saveAuth = useCallback((data) => {
    localStorage.setItem(storageKey(roomId), JSON.stringify(data))
    setAuthState(data)
  }, [roomId])

  const clearAuth = useCallback(() => {
    localStorage.removeItem(storageKey(roomId))
    setAuthState(null)
  }, [roomId])

  return { auth, saveAuth, clearAuth }
}
