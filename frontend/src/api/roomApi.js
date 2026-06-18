const BASE_URL = import.meta.env.VITE_API_URL || ''

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = e.detail || msg } catch {}
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
