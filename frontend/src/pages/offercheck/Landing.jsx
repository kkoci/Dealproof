import React from 'react'
import { Link } from 'react-router-dom'
import logo from '../../assets/icon.svg'

export default function Landing() {
  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col">
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-16 sm:py-24">
        <div className="w-full max-w-2xl mx-auto text-center">
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 rounded-2xl bg-bg-surface border border-border flex items-center justify-center" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
              <img src={logo} alt="Offer Check" className="w-9 h-9" />
            </div>
          </div>

          <h1 className="text-4xl sm:text-5xl font-bold text-ink-primary mb-4 tracking-tight">
            Offer Check
          </h1>
          <p className="text-base sm:text-lg text-ink-secondary font-medium mb-6">
            Verify a competing offer without revealing either side's numbers
          </p>
          <p className="text-sm sm:text-base text-ink-muted max-w-lg mx-auto leading-relaxed mb-10">
            You get a gap percentage. Nothing else crosses the line. Candidates never
            see the employer's salary band, and employers never see the candidate's
            offer letter or raw ask — just the gap, round by round, until you converge.
          </p>

          {/* luxe SKILL.md Press Feedback: scale(0.96) on :active, layered on top of the existing
              hover-lift (translateY) rather than replacing it — applied to BOTH CTAs together so the
              paired buttons stay visually consistent with each other (see docs/design/luxe audit notes
              on why this isn't extended to CandidateNew.jsx / Dashboard.jsx). */}
          <div className="flex flex-col sm:flex-row justify-center gap-3 mb-16">
            <Link
              to="/offercheck/new"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl bg-teal hover:bg-teal-hover text-white font-semibold text-base transition-[background-color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.96] active:duration-100"
            >
              I'm the candidate — start verification
            </Link>
            <Link
              to="/offercheck/company/new"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl bg-transparent border-[1.5px] border-border-strong hover:bg-bg-elevated text-ink-primary font-semibold text-base transition-[background-color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.96] active:duration-100"
            >
              I'm the employer — start a negotiation
            </Link>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left">
            {[
              { step: '01', title: 'Candidate submits', desc: 'Enter your competing offer and your ask. Get a link to send the employer.' },
              { step: '02', title: 'Employer responds', desc: 'They enter their private band and see only the gap — never your numbers.' },
              { step: '03', title: 'Revise until it converges', desc: 'Both sides counter, up to 5 rounds, until you agree or walk away.' },
            ].map((item) => (
              <div key={item.step} className="p-4 rounded-xl bg-bg-surface border border-border" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
                <div className="text-xs font-mono text-teal mb-2">{item.step}</div>
                <h3 className="text-sm font-semibold text-ink-primary mb-1.5">{item.title}</h3>
                <p className="text-xs text-ink-muted leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>

          <p className="text-xs text-ink-muted mt-10">
            Every agreement is verified by secure, tamper-proof hardware — cryptographic proof neither side altered the result.
          </p>
        </div>
      </div>
    </div>
  )
}
