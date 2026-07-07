import React from 'react'
import { Link } from 'react-router-dom'

export default function Landing() {
  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col">
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-16 sm:py-24">
        <div className="w-full max-w-2xl mx-auto text-center">
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 rounded-2xl bg-emerald-600 flex items-center justify-center shadow-2xl shadow-emerald-900/60">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>

          <h1 className="text-4xl sm:text-5xl font-bold text-white mb-4 tracking-tight">
            Offer Check
          </h1>
          <p className="text-base sm:text-lg text-gray-400 font-medium mb-6">
            Verify a competing offer without revealing either side's numbers
          </p>
          <p className="text-sm sm:text-base text-gray-500 max-w-lg mx-auto leading-relaxed mb-10">
            You get a gap percentage. Nothing else crosses the line. Candidates never
            see the employer's salary band, and employers never see the candidate's
            offer letter or raw ask — just the gap, round by round, until you converge.
          </p>

          <div className="flex justify-center mb-16">
            <Link
              to="/offercheck/new"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-base transition-all shadow-lg shadow-emerald-900/40 hover:-translate-y-0.5 active:translate-y-0"
            >
              I'm the candidate — start verification
            </Link>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left">
            {[
              { step: '01', title: 'Candidate submits', desc: 'Enter your competing offer and your ask. Get a link to send the employer.' },
              { step: '02', title: 'Employer responds', desc: 'They enter their private band and see only the gap — never your numbers.' },
              { step: '03', title: 'Revise until it converges', desc: 'Both sides counter, up to 5 rounds, until you agree or walk away.' },
            ].map((item) => (
              <div key={item.step} className="p-4 rounded-xl bg-gray-900/40 border border-gray-800/40">
                <div className="text-xs font-mono text-emerald-500 mb-2">{item.step}</div>
                <h3 className="text-sm font-semibold text-gray-200 mb-1.5">{item.title}</h3>
                <p className="text-xs text-gray-500 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>

          <p className="text-xs text-gray-600 mt-10">
            Phase 1 proof of concept — software verification only, no hardware attestation yet.
          </p>
        </div>
      </div>
    </div>
  )
}
