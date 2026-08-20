import React from 'react'

// Placeholder — no real About/company/team content exists yet for this vertical. Deliberately
// kept to the same factual product description already used on Landing.jsx rather than
// inventing team bios, funding claims, or a founding story that isn't real. Replace this with
// real content when it exists.
export default function About() {
  return (
    <div className="px-4 sm:px-6 lg:px-8">
      <div className="max-w-2xl mx-auto py-16">
        <h1 className="font-display text-hero-sm text-ink-primary mb-4">About Offer Check</h1>
        <p className="text-sm text-ink-secondary leading-relaxed mb-4">
          Offer Check verifies a candidate's competing offer against an employer's salary band
          without either side revealing their private numbers. The negotiation runs inside a
          Trusted Execution Environment, and a hardware-signed attestation proves the process
          ran exactly as claimed.
        </p>
        <p className="text-xs text-ink-muted">
          This page is a placeholder — more about the team and company will go here.
        </p>
      </div>
    </div>
  )
}
