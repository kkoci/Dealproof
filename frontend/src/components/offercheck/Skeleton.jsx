// Static loading placeholder — deliberately no pulse/shimmer animation in this pass (motion is out of
// scope for the visual-identity prompt; the follow-up interaction pass is the natural place to decide
// whether loading states should breathe). Flat bg-elevated blocks read as "not ready yet" without
// motion doing the telling.
import React from 'react'

export function SkeletonLine({ width = 'w-full', height = 'h-4', className = '' }) {
  return <div className={`${width} ${height} rounded bg-bg-elevated ${className}`} />
}

export function SkeletonBlock({ className = '' }) {
  return <div className={`rounded-xl bg-bg-elevated ${className}`} />
}
