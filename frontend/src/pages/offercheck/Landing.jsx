import React from 'react'
import { Link } from 'react-router-dom'
import Card from '../../components/offercheck/Card.jsx'
import { SealMark } from '../../components/offercheck/Seal.jsx'
import { SealIcon } from '../../components/offercheck/icons.jsx'

const ctaBase =
  'w-full sm:w-auto focus-ring inline-flex items-center justify-center gap-2 px-8 h-12 rounded-xl font-semibold text-sm ' +
  'transition-[background-color,border-color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] ' +
  'active:scale-[0.96] active:duration-100'

export default function Landing() {
  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col">
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-16 sm:py-24">
        <div className="w-full max-w-2xl mx-auto text-center">
          <div className="flex justify-center mb-6">
            <SealMark size="lg" />
          </div>

          <h1 className="text-hero sm:text-[2.75rem] text-ink-primary mb-4">
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

          <div className="flex flex-col sm:flex-row justify-center gap-3 mb-16">
            <Link to="/offercheck/new" className={`${ctaBase} bg-teal hover:bg-teal-hover text-white border border-transparent`}>
              I'm the candidate — start verification
            </Link>
            <Link
              to="/offercheck/company/new"
              className={`${ctaBase} bg-transparent border-[1.5px] border-border-strong hover:bg-bg-elevated text-ink-primary`}
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
              <Card key={item.step} padding="sm">
                <div className="text-xs font-mono tnum text-teal mb-2">{item.step}</div>
                <h3 className="text-sm font-semibold text-ink-primary mb-1.5">{item.title}</h3>
                <p className="text-xs text-ink-muted leading-relaxed">{item.desc}</p>
              </Card>
            ))}
          </div>

          <p className="flex items-center justify-center gap-1.5 text-xs text-ink-muted mt-10">
            <SealIcon size={14} className="text-teal shrink-0" />
            Every agreement is verified by hardware — cryptographic proof neither side altered the result.
          </p>
        </div>
      </div>
    </div>
  )
}
