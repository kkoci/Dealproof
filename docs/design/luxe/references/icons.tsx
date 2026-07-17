// =============================================================================
// luxe — Starter Icon Set
// =============================================================================
//
// Custom stroke icons in the luxe house style. Every icon:
//   • fill="none", stroke="currentColor" — inherits text color, themes for free
//   • strokeWidth 1.5, round caps + joins
//   • 16×16 viewBox (14 for the checkbox glyph), sized via a `size` prop
//
// Zero dependencies, zero external CSS — drop this file in and import.
// Modeled on Benji Taylor's Agentation icon system (the "Benji" half of luxe).
// Techniques only; geometry is original / trivial. Swap/extend freely.
//
// Animated variants (IconCopyCheck, IconPausePlay, IconEyeToggle) crossfade
// between two states via inline transitions on transform/opacity/stroke —
// no @keyframes, no runtime motion lib, so the file stays self-contained.
// =============================================================================

import type { CSSProperties } from "react";

type IconProps = { size?: number; className?: string };

const base = (size: number, vb = 16) => ({
  width: size,
  height: size,
  viewBox: `0 0 ${vb} ${vb}`,
  fill: "none" as const,
  xmlns: "http://www.w3.org/2000/svg",
});

const stroke = {
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

// --- Structural ------------------------------------------------------------

export const IconClose = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M4 4l8 8M12 4l-8 8" {...stroke} />
  </svg>
);

export const IconPlus = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M8 3v10M3 8h10" {...stroke} />
  </svg>
);

export const IconCheck = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M3 8l3.5 3.5L13 5" {...stroke} />
  </svg>
);

// Optimized for a 14px checkbox glyph (pairs with the Checkbox Draw Effect).
export const IconCheckSmall = ({ size = 14, className }: IconProps) => (
  <svg {...base(size, 14)} className={className}>
    <path d="M3.9 7l2.2 2.2L10.5 4.8" {...stroke} />
  </svg>
);

export const IconChevronRight = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M6 4l4 4-4 4" {...stroke} />
  </svg>
);

export const IconChevronLeft = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M10 4L6 8l4 4" {...stroke} />
  </svg>
);

// Chevron that rotates 180° on open — pass `open` (e.g. a select trigger).
export const IconChevronDown = ({
  size = 16,
  className,
  open = false,
}: IconProps & { open?: boolean }) => (
  <svg
    {...base(size)}
    className={className}
    style={{
      transform: open ? "rotate(180deg)" : "rotate(0deg)",
      transition: "transform 180ms cubic-bezier(0.22, 1, 0.36, 1)",
    }}
  >
    <path d="M4 6l4 4 4-4" {...stroke} />
  </svg>
);

// --- Glyphs ----------------------------------------------------------------

export const IconGear = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="8" cy="8" r="2.25" {...stroke} />
    <path
      d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4"
      {...stroke}
    />
  </svg>
);

export const IconTrash = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 8h6l.5-8M7 7v3M9 7v3" {...stroke} />
  </svg>
);

export const IconHelp = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="8" cy="8" r="6" {...stroke} />
    <path d="M6.2 6.2a1.8 1.8 0 013.4.8c0 1.2-1.6 1.4-1.6 2.6" {...stroke} />
    <circle cx="8" cy="11.4" r="0.6" fill="currentColor" stroke="none" />
  </svg>
);

export const IconSun = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <circle cx="8" cy="8" r="3" {...stroke} />
    <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.1 3.1l1.4 1.4M11.5 11.5l1.4 1.4M12.9 3.1l-1.4 1.4M4.5 11.5l-1.4 1.4" {...stroke} />
  </svg>
);

export const IconMoon = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M13 9.5A5.5 5.5 0 116.5 3 4.5 4.5 0 0013 9.5z" {...stroke} />
  </svg>
);

export const IconSend = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M13.5 2.5L7 9M13.5 2.5l-4 11-2.5-4.5L2.5 6l11-3.5z" {...stroke} />
  </svg>
);

export const IconEdit = ({ size = 16, className }: IconProps) => (
  <svg {...base(size)} className={className}>
    <path d="M11 2.5l2.5 2.5M12 1.5l2.5 2.5-8 8L3 13l1-3.5 8-8z" {...stroke} />
  </svg>
);

// --- Animated variants (self-contained, no keyframes) ----------------------

// Copy → checkmark morph. Drive `copied` from your click handler; the check
// draws in via stroke-dashoffset (the Checkbox Draw Effect) while the two
// copy rectangles fade out. Asymmetric: 200ms in (draw), 100ms out.
export const IconCopyCheck = ({
  size = 16,
  className,
  copied = false,
}: IconProps & { copied?: boolean }) => (
  <svg {...base(size)} className={className}>
    <g
      style={{
        opacity: copied ? 0 : 1,
        transition: `opacity ${copied ? 100 : 200}ms cubic-bezier(0.22, 1, 0.36, 1)`,
      }}
    >
      <rect x="5.5" y="5.5" width="8" height="8" rx="2" {...stroke} />
      <path d="M10.5 5.5V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v4a2 2 0 002 2h1.5" {...stroke} />
    </g>
    <path
      d="M5 8.2l2.2 2.2L11.5 6"
      {...stroke}
      style={{
        strokeDasharray: 10,
        strokeDashoffset: copied ? 0 : 10,
        opacity: copied ? 1 : 0,
        transition: copied
          ? "stroke-dashoffset 200ms cubic-bezier(0.34, 1.56, 0.64, 1), opacity 120ms"
          : "stroke-dashoffset 100ms, opacity 100ms",
      }}
    />
  </svg>
);

// Pause ↔ play crossfade. Two groups, scale+opacity swap on the overshoot curve.
export const IconPausePlay = ({
  size = 16,
  className,
  playing = false,
}: IconProps & { playing?: boolean }) => {
  const swap = (show: boolean): CSSProperties => ({
    opacity: show ? 1 : 0,
    transform: show ? "scale(1)" : "scale(0.8)",
    transformOrigin: "center",
    transition: "opacity 160ms, transform 200ms cubic-bezier(0.34, 1.56, 0.64, 1)",
  });
  return (
    <svg {...base(size)} className={className}>
      <g style={swap(playing)}>
        <path d="M6 4v8M10 4v8" {...stroke} />
      </g>
      <g style={swap(!playing)}>
        <path d="M5.5 4l7 4-7 4V4z" {...stroke} />
      </g>
    </svg>
  );
};

// Eye ↔ eye-off. The slash draws in via stroke-dashoffset when hidden.
export const IconEyeToggle = ({
  size = 16,
  className,
  off = false,
}: IconProps & { off?: boolean }) => (
  <svg {...base(size)} className={className}>
    <path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" {...stroke} />
    <circle cx="8" cy="8" r="2" {...stroke} />
    <path
      d="M2.5 2.5l11 11"
      {...stroke}
      style={{
        strokeDasharray: 16,
        strokeDashoffset: off ? 0 : 16,
        transition: "stroke-dashoffset 200ms cubic-bezier(0.34, 1.56, 0.64, 1)",
      }}
    />
  </svg>
);

// -- Convenience registry (for pickers / iteration) -------------------------
export const luxeIcons = {
  close: IconClose,
  plus: IconPlus,
  check: IconCheck,
  checkSmall: IconCheckSmall,
  chevronRight: IconChevronRight,
  chevronLeft: IconChevronLeft,
  chevronDown: IconChevronDown,
  gear: IconGear,
  trash: IconTrash,
  help: IconHelp,
  sun: IconSun,
  moon: IconMoon,
  send: IconSend,
  edit: IconEdit,
} as const;
