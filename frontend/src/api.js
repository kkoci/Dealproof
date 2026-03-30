const BASE_URL = import.meta.env.VITE_API_URL || ''

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!res.ok) {
    let errorMessage = `HTTP ${res.status}: ${res.statusText}`
    try {
      const errBody = await res.json()
      if (errBody.detail) {
        errorMessage = typeof errBody.detail === 'string'
          ? errBody.detail
          : JSON.stringify(errBody.detail)
      }
    } catch {
      // ignore parse errors
    }
    throw new Error(errorMessage)
  }

  return res.json()
}

/**
 * GET /health
 * @returns {{ status: string, tee_mode: string }}
 */
export function getHealth() {
  return request('/health')
}

/**
 * POST /api/deals/run — create and negotiate in one call
 * @param {object} body
 * @returns {Promise<DealResult>}
 */
export function runDeal(body) {
  return request('/api/deals/run', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/deals — create deal only (status=pending)
 * @param {object} body
 * @returns {Promise<DealStatus>}
 */
export function createDeal(body) {
  return request('/api/deals', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/deals/:id/negotiate
 * @param {string} id
 * @returns {Promise<DealResult>}
 */
export function negotiateDeal(id) {
  return request(`/api/deals/${id}/negotiate`, { method: 'POST' })
}

/**
 * GET /api/deals/:id/status
 * @param {string} id
 * @returns {Promise<DealStatus>}
 */
export function getDealStatus(id) {
  return request(`/api/deals/${id}/status`)
}

/**
 * GET /api/deals/:id/attestation
 * @param {string} id
 * @returns {Promise<{ deal_id: string, attestation: string }>}
 */
export function getDealAttestation(id) {
  return request(`/api/deals/${id}/attestation`)
}

/**
 * GET /api/deals/:id/dcap-verify
 * @param {string} id
 * @returns {Promise<DCAPVerification>}
 */
export function getDcapVerification(id) {
  return request(`/api/deals/${id}/dcap-verify`)
}

/**
 * GET /api/deals/:id/verification
 * @param {string} id
 * @returns {Promise<{ deal_id: string, verification: object }>}
 */
export function getDealVerification(id) {
  return request(`/api/deals/${id}/verification`)
}
