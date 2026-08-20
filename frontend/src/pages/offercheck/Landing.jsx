import React from 'react'
import { Link } from 'react-router-dom'
import Card from '../../components/offercheck/Card.jsx'
import BalanceMeter from '../../components/offercheck/BalanceMeter.jsx'
import { SealMark } from '../../components/offercheck/Seal.jsx'
import { SealIcon } from '../../components/offercheck/icons.jsx'

const ctaBase =
  'w-full sm:w-auto focus-ring inline-flex items-center justify-center gap-2 px-7 h-12 rounded-lg font-semibold text-sm ' +
  'transition-[background-color,border-color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] ' +
  'active:scale-[0.96] active:duration-100'

const STEPS = [
  { n: '01', title: 'Candidate submits', desc: "Enter your competing offer and your ask. Get a link to send the employer — nothing on this side ever leaves the enclave in the clear." },
  { n: '02', title: 'Employer responds', desc: 'They enter their private band and see only the gap — never your numbers, never even a range.' },
  { n: '03', title: 'Revise until it converges', desc: 'Both sides counter, up to 5 rounds, until you agree or walk away — then hardware signs the outcome.' },
]

export default function Landing() {
  return (
    <div className="px-4 sm:px-6 lg:px-8">
      <div className="max-w-6xl mx-auto">
        {/* Hero — deliberately asymmetric: left column carries the argument, right column is an
            off-axis preview of the instrument itself, overlapping the grid line on purpose. */}
        <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-10 lg:gap-6 items-center pt-16 pb-20 sm:pt-24 sm:pb-28">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-border-strong bg-bg-surface mb-7">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-pulse-slow absolute inline-flex h-full w-full rounded-full bg-gap-zero" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-gap-zero" />
              </span>
              <span className="text-data-label uppercase text-ink-secondary">Negotiated inside an Intel TDX enclave</span>
            </div>

            <h1 className="font-display font-semibold text-[2.75rem] sm:text-[3.75rem] leading-[0.98] tracking-tight text-ink-primary mb-6">
              Prove the number,<br />not just claim it.
            </h1>

            <p className="text-base text-ink-secondary leading-relaxed max-w-md mb-9">
              Offer Check verifies a competing offer without either side seeing the other's raw
              numbers. Two agents negotiate inside a confidential enclave; you get a gap percentage
              round by round, and a hardware-signed proof once you converge.
            </p>

            <div className="flex flex-col sm:flex-row gap-3">
              <Link to="/offercheck/new" className={`${ctaBase} bg-teal hover:bg-teal-hover text-ink-inverse border border-transparent`}>
                I'm the candidate
              </Link>
              <Link
                to="/offercheck/company/new"
                className={`${ctaBase} bg-transparent border-[1.5px] border-border-strong hover:bg-bg-elevated hover:border-teal/50 text-ink-primary`}
              >
                I'm the employer
              </Link>
            </div>
          </div>

          {/* The instrument, previewed — sits slightly off the grid line and tilted, like something
              resting on a desk rather than snapped to the layout. This is the moment worth
              screenshotting: it's what every negotiation resolves down to. */}
          <div className="relative lg:-ml-10">
            <div className="hidden lg:block absolute -inset-x-8 -inset-y-10 rounded-[2rem] bg-teal/[0.04] blur-2xl pointer-events-none" />
            <Card
              emphasis="spotlight"
              padding="lg"
              className="relative mx-auto max-w-xs sm:max-w-sm lg:rotate-[-2deg] lg:hover:rotate-0 transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-data-label uppercase text-ink-muted">Live instrument</span>
                <span className="text-[10px] uppercase tracking-wide text-ink-muted/70 font-mono">preview</span>
              </div>
              <BalanceMeter gapPct={9.2} label="" />
              <p className="text-xs text-ink-muted text-center mt-1">
                Illustrative reading — not a real session
              </p>
            </Card>
          </div>
        </div>

        {/* Process — a staggered descent instead of three level cards, with an oversized ghost
            numeral behind each step as the typographic device carrying the "breaking the grid" risk. */}
        <div className="border-t border-border pt-14 pb-20">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 sm:gap-4">
            {STEPS.map((item, i) => (
              <div key={item.n} className={i === 1 ? 'sm:mt-8' : i === 2 ? 'sm:mt-16' : ''}>
                <div className="relative">
                  <span
                    aria-hidden="true"
                    className="font-display absolute -top-6 -left-1 text-[5rem] font-semibold text-ink-primary/[0.05] select-none leading-none"
                  >
                    {item.n}
                  </span>
                  <div className="relative pt-6">
                    <div className="w-8 h-px bg-teal mb-4" />
                    <h3 className="text-sm font-semibold text-ink-primary mb-2">{item.title}</h3>
                    <p className="text-sm text-ink-muted leading-relaxed">{item.desc}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-border py-10">
          <p className="flex items-center justify-center gap-2 text-xs text-ink-muted">
            <SealIcon size={14} className="text-teal shrink-0" />
            Every agreement is verified by hardware — cryptographic proof neither side altered the result.
          </p>
        </div>
      </div>
    </div>
  )
}
