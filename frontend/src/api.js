const BASE_URL = import.meta.env.VITE_API_URL || ''

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  const { headers, ...restOptions } = options
  const res = await fetch(url, {
    ...restOptions,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
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

async function requestMultipart(path, formData) {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, { method: 'POST', body: formData })

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

// ---------------------------------------------------------------------------
// Offer Check (vertical/hr-offer-check) — /api/offercheck/*
// ---------------------------------------------------------------------------

/**
 * POST /api/offercheck/sessions — candidate submits competing offer + ask
 * @param {object} body { competing_offer, candidate_ask }
 * @returns {Promise<object>} CandidateSubmitResponse
 */
export function offercheckSubmit(body) {
  return request('/api/offercheck/sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/employer/band — one-time private band submission
 * @param {string} sessionId
 * @param {object} body { employer_token, band_min, band_mid, band_max }
 * @returns {Promise<object>} EmployerBandResponse
 */
export function offercheckSetEmployerBand(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/employer/band`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/employer/move
 * @param {string} sessionId
 * @param {object} body { token, move, value }
 * @returns {Promise<object>} SessionView
 */
export function offercheckEmployerMove(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/employer/move`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/candidate/move
 * @param {string} sessionId
 * @param {object} body { token, move, value }
 * @returns {Promise<object>} SessionView
 */
export function offercheckCandidateMove(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/candidate/move`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/employer/approval — vote at the PENDING_APPROVAL checkpoint
 * @param {string} sessionId
 * @param {object} body { token, decision: "approve" | "request_more_rounds" | "decline" }
 * @returns {Promise<object>} SessionView
 */
export function offercheckEmployerApproval(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/employer/approval`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/candidate/approval — candidate's counterpart to the above
 * @param {string} sessionId
 * @param {object} body { token, decision: "approve" | "request_more_rounds" | "decline" }
 * @returns {Promise<object>} SessionView
 */
export function offercheckCandidateApproval(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/candidate/approval`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/employer/approval-package — package-mode counterpart
 * @param {string} sessionId
 * @param {object} body { token, decision: "approve" | "request_more_rounds" | "decline" }
 * @returns {Promise<object>} SessionView
 */
export function offercheckEmployerApprovalPackage(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/employer/approval-package`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/sessions/:id/candidate/approval-package — candidate's counterpart
 * @param {string} sessionId
 * @param {object} body { token, decision: "approve" | "request_more_rounds" | "decline" }
 * @returns {Promise<object>} SessionView
 */
export function offercheckCandidateApprovalPackage(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/candidate/approval-package`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/**
 * GET /api/offercheck/sessions/:id?token=... — viewer-scoped status poll
 * @param {string} sessionId
 * @param {string} token
 * @returns {Promise<object>} SessionView
 */
export function offercheckGetSession(sessionId, token) {
  return request(`/api/offercheck/sessions/${sessionId}?token=${encodeURIComponent(token)}`)
}

/**
 * PATCH /api/offercheck/sessions/:id/candidate/enable-agentic — seal candidate_floor any time before terminal
 * @param {string} sessionId
 * @param {{ token: string, candidate_floor: number, candidate_priorities?: string }} body
 * @returns {Promise<object>} SessionView
 */
export function offercheckEnableCandidateAgentic(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/candidate/enable-agentic`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/**
 * PATCH /api/offercheck/sessions/:id/employer/enable-agentic — seal employer_authority_limit any time before terminal
 * @param {string} sessionId
 * @param {{ token: string, employer_authority_limit: number, employer_priorities?: string }} body
 * @returns {Promise<object>} SessionView
 */
export function offercheckEnableEmployerAgentic(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/employer/enable-agentic`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/**
 * PATCH /api/offercheck/sessions/:id/candidate/enable-agentic-package — seal candidate_total_comp_floor any time before terminal
 * @param {string} sessionId
 * @param {{ token: string, candidate_total_comp_floor: number, candidate_package_priorities?: string }} body
 * @returns {Promise<object>} SessionView
 */
export function offercheckEnableCandidatePackageAgentic(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/candidate/enable-agentic-package`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/**
 * PATCH /api/offercheck/sessions/:id/employer/enable-agentic-package — seal employer_total_comp_budget any time before terminal
 * @param {string} sessionId
 * @param {{ token: string, employer_total_comp_budget: number, employer_priorities?: string }} body
 * @returns {Promise<object>} SessionView
 */
export function offercheckEnableEmployerPackageAgentic(sessionId, body) {
  return request(`/api/offercheck/sessions/${sessionId}/employer/enable-agentic-package`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/**
 * POST /api/offercheck/parse-offer-letter — upload a PDF, get draft fields to review
 * @param {File} file
 * @returns {Promise<object>} OfferLetterExtraction { competing_offer, confidence, notes }
 */
export function offercheckParseOfferLetter(file) {
  const formData = new FormData()
  formData.append('file', file)
  return requestMultipart('/api/offercheck/parse-offer-letter', formData)
}

/**
 * GET /api/offercheck/sessions/:id/attest?token=... — TDX attestation receipt (terminal states only)
 * @param {string} sessionId
 * @param {string} token
 * @returns {Promise<object>} AttestationReceipt
 */
export function offercheckGetAttestation(sessionId, token) {
  return request(`/api/offercheck/sessions/${sessionId}/attest?token=${encodeURIComponent(token)}`)
}

/**
 * POST /api/offercheck/sessions/:id/start-agentic — run CandidateAgent vs EmployerAgent to completion.
 * Requires a party token OR a demo token (X-Demo-Token) — see app.offercheck.demo_auth.
 * @param {string} sessionId
 * @param {{ token?: string, demoToken?: string }} auth
 * @returns {Promise<object>} AgenticResult
 */
export function offercheckStartAgentic(sessionId, { token, demoToken } = {}) {
  const headers = {}
  if (demoToken) headers['X-Demo-Token'] = demoToken
  return request(`/api/offercheck/sessions/${sessionId}/start-agentic`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ token: token || null }),
  })
}

/**
 * POST /api/offercheck/sessions/:id/start-agentic-package — full compensation package negotiation (Phase 2B)
 * @param {string} sessionId
 * @param {{ token?: string, demoToken?: string }} auth
 * @returns {Promise<object>} PackageAgenticResult
 */
export function offercheckStartAgenticPackage(sessionId, { token, demoToken } = {}) {
  const headers = {}
  if (demoToken) headers['X-Demo-Token'] = demoToken
  return request(`/api/offercheck/sessions/${sessionId}/start-agentic-package`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ token: token || null }),
  })
}

/**
 * GET /api/offercheck/auth/verify — check a magic-link demo token's validity
 * @param {string} token
 * @param {string} sessionId
 * @returns {Promise<object>} VerifyTokenResponse
 */
export function offercheckVerifyDemoToken(token, sessionId) {
  return request(`/api/offercheck/auth/verify?token=${encodeURIComponent(token)}&session=${encodeURIComponent(sessionId)}`)
}

/**
 * GET /api/offercheck/sessions/:id/dcap-verify?token=... — parsed DCAP quote fields
 * @param {string} sessionId
 * @param {string} token
 * @returns {Promise<object>} DcapVerification
 */
export function offercheckGetDcapVerify(sessionId, token) {
  return request(`/api/offercheck/sessions/${sessionId}/dcap-verify?token=${encodeURIComponent(token)}`)
}

/**
 * GET /api/offercheck/sessions/:id/credential — either ?token=... or an X-API-Key header
 * @param {string} sessionId
 * @param {{ token?: string, apiKey?: string }} auth
 * @returns {Promise<object>} CredentialResponse
 */
export function offercheckGetCredential(sessionId, { token, apiKey } = {}) {
  if (apiKey) {
    return request(`/api/offercheck/sessions/${sessionId}/credential`, { headers: { 'X-API-Key': apiKey } })
  }
  return request(`/api/offercheck/sessions/${sessionId}/credential?token=${encodeURIComponent(token)}`)
}

/**
 * POST /api/offercheck/company/register
 * @param {{ name: string, hires_per_year?: number }} body
 * @returns {Promise<object>} CompanyRegisterResponse — api_key is shown exactly once
 */
export function offercheckRegisterCompany(body) {
  return request('/api/offercheck/company/register', { method: 'POST', body: JSON.stringify(body) })
}

/**
 * POST /api/offercheck/company/ats-connect
 * @param {string} apiKey
 * @param {{ provider: string, api_key: string }} body
 * @returns {Promise<object>} AtsConnectResponse
 */
export function offercheckConnectAts(apiKey, body) {
  return request('/api/offercheck/company/ats-connect', {
    method: 'POST',
    headers: { 'X-API-Key': apiKey },
    body: JSON.stringify(body),
  })
}

/**
 * GET /api/offercheck/company/sessions
 * @param {string} apiKey
 * @returns {Promise<object>} CompanySessionsResponse
 */
export function offercheckListCompanySessions(apiKey) {
  return request('/api/offercheck/company/sessions', { headers: { 'X-API-Key': apiKey } })
}

/**
 * Classifies a stored/entered company API key before any authenticated UI renders, so a stale
 * key (e.g. left over in localStorage from before a backend restart wiped the in-memory company
 * store) never surfaces as a raw "invalid API key" error — it reads as "no company registered
 * yet" instead, since that's what it actually is.
 *
 * 'empty'        — no key at all
 * 'malformed'    — doesn't look like a key this backend issues (heuristic: "oc_" prefix,
 *                  matches auth.register_company's raw_key format) — the one case that's
 *                  actually "you typed something wrong"
 * 'unregistered' — well-formed but the backend has no record of it (never registered, or
 *                  registered against a since-restarted server instance) — NOT a typo
 * 'valid'        — backend confirms it resolves to a real company
 *
 * @param {string} apiKey
 * @returns {Promise<'empty'|'malformed'|'unregistered'|'valid'>}
 */
export async function offercheckCheckCompanyKey(apiKey) {
  if (!apiKey) return 'empty'
  if (!apiKey.startsWith('oc_')) return 'malformed'
  try {
    await offercheckListCompanySessions(apiKey)
    return 'valid'
  } catch {
    return 'unregistered'
  }
}

/**
 * POST /api/offercheck/company/verify/bulk
 * @param {string} apiKey
 * @param {{ verifications: object[] }} body
 * @returns {Promise<object>} BulkVerifyResponse
 */
export function offercheckBulkVerify(apiKey, body) {
  return request('/api/offercheck/company/verify/bulk', {
    method: 'POST',
    headers: { 'X-API-Key': apiKey },
    body: JSON.stringify(body),
  })
}

// ---------------------------------------------------------------------------
// Employer-initiated invites — mirror of the candidate-initiated flow above
// ---------------------------------------------------------------------------

/**
 * POST /api/offercheck/employer/new — authenticated employer opens an invite before any candidate exists
 * @param {string} apiKey
 * @param {{ band_min: number, band_mid: number, band_max: number, requirements?: string, employer_authority_limit?: number, employer_priorities?: string }} body
 * @returns {Promise<object>} EmployerInviteResponse { invite_id, candidate_join_link, status }
 */
export function offercheckCreateInvite(apiKey, body) {
  return request('/api/offercheck/employer/new', {
    method: 'POST',
    headers: { 'X-API-Key': apiKey },
    body: JSON.stringify(body),
  })
}

/**
 * GET /api/offercheck/employer/invite/:inviteId — status check for the invite's own creating company
 * @param {string} apiKey
 * @param {string} inviteId
 * @returns {Promise<object>} InviteStatusResponse { invite_id, status, session_id, employer_token }
 */
export function offercheckGetInvite(apiKey, inviteId) {
  return request(`/api/offercheck/employer/invite/${inviteId}`, { headers: { 'X-API-Key': apiKey } })
}

/**
 * POST /api/offercheck/candidate/join/:inviteId — candidate claims an employer-initiated invite
 * @param {string} inviteId
 * @param {object} body { competing_offer, candidate_ask, candidate_floor?, candidate_priorities? }
 * @returns {Promise<object>} CandidateSubmitResponse — same shape as offercheckSubmit's response
 */
export function offercheckJoinInvite(inviteId, body) {
  return request(`/api/offercheck/candidate/join/${inviteId}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
