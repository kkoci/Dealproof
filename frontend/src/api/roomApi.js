const BASE_URL = import.meta.env.VITE_API_URL || ''

async function request(path, options = {}) {
  const { headers: extraHeaders, ...restOptions } = options
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...extraHeaders },
    ...restOptions,
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const e = await res.json()
      if (typeof e.detail === 'string') msg = e.detail
      else if (Array.isArray(e.detail)) msg = e.detail.map(d => d.msg || JSON.stringify(d)).join('; ')
      else if (e.detail) msg = JSON.stringify(e.detail)
    } catch {}
    throw new Error(msg)
  }
  return res.json()
}

export function registerSeller(body) {
  return request('/api/room/seller/register', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function registerBuyer(body) {
  return request('/api/room/buyer/register', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getRoomStatus(roomId) {
  return request(`/api/room/${roomId}/status`)
}

export function saveRoomConfig(roomId, token, config) {
  return request(`/api/room/${roomId}/config`, {
    method: 'PUT',
    headers: { 'x-room-token': token },
    body: JSON.stringify(config),
  })
}

export function confirmRoom(roomId, token) {
  return request(`/api/room/${roomId}/confirm`, {
    method: 'POST',
    headers: { 'x-room-token': token },
  })
}

export function startRoomDeal(roomId, token) {
  return request(`/api/room/${roomId}/start`, {
    method: 'POST',
    headers: { 'x-room-token': token },
  })
}
