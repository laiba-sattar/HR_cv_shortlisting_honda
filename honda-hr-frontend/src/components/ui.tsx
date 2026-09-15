import React from "react";

// ---------------------------------------------------------------------------
// Shared primitives. Everything visual that appears on more than one page
// lives here, so a change to the look is one edit rather than twenty.
// ---------------------------------------------------------------------------

export const Card: React.FC<
  React.HTMLAttributes<HTMLDivElement> & { padded?: boolean; flush?: boolean }
> = ({ className = "", padded = true, flush = false, children, ...rest }) => (
  <div
    className={`rounded-xl2 border border-cream-200 bg-white ${
      flush ? "" : "shadow-card"
    } ${padded ? "p-5 sm:p-6" : ""} ${className}`}
    {...rest}
  >
    {children}
  </div>
);

/** The header strip inside a flush Card — title left, controls right. */
export const CardHead: React.FC<{
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  className?: string;
}> = ({ title, subtitle, action, className = "" }) => (
  <div
    className={`flex flex-col gap-3 border-b border-cream-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6 ${className}`}
  >
    <div className="min-w-0">
      <h3 className="text-md font-semibold text-ink-900">{title}</h3>
      {subtitle && <p className="mt-0.5 text-sm text-ink-500">{subtitle}</p>}
    </div>
    {action && <div className="shrink-0">{action}</div>}
  </div>
);

export const SectionTitle: React.FC<{
  eyebrow?: string;
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  className?: string;
}> = ({ eyebrow, title, subtitle, action, className = "" }) => (
  <div className={`flex items-end justify-between gap-6 ${className}`}>
    <div className="min-w-0">
      {/* The same short red rule the panel headings carry, so a page title and
          a panel title are visibly the same kind of thing. */}
      {eyebrow && (
        <p className="label mb-2 flex items-center gap-2">
          <span aria-hidden className="h-3 w-[3px] rounded-full bg-honda-red" />
          {eyebrow}
        </p>
      )}
      <h2 className="text-2xl font-semibold text-ink-900">{title}</h2>
      {subtitle && <p className="mt-1.5 max-w-[62ch] text-md text-ink-500">{subtitle}</p>}
    </div>
    {action && <div className="shrink-0">{action}</div>}
  </div>
);

// ---------------------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const variantClasses: Record<ButtonVariant, string> = {
  // The shadow is tinted with the button's own red rather than grey. A grey
  // shadow under a saturated colour reads as dirt; a shadow of the same hue
  // reads as the button glowing very slightly onto the page, which is what
  // makes a solid-colour button look pressed out of the surface rather than
  // pasted onto it. It lifts on hover and goes flat on the press.
  primary:
    "bg-honda-red text-white shadow-[0_1px_2px_rgba(140,26,30,0.28),0_8px_18px_-8px_rgba(140,26,30,0.55)] " +
    "hover:bg-honda-red-dark hover:shadow-[0_2px_4px_rgba(140,26,30,0.30),0_12px_24px_-10px_rgba(140,26,30,0.62)] " +
    "active:bg-honda-red-darker active:shadow-none " +
    "disabled:bg-cream-200 disabled:text-ink-300 disabled:shadow-none",
  secondary:
    "bg-wine-800 text-white shadow-xs hover:bg-wine-700 active:bg-wine-900 " +
    "disabled:bg-cream-200 disabled:text-ink-300 disabled:shadow-none",
  // Secondary actions carry the brand tint rather than being white boxes with
  // grey type. They are NOT solid red: if every button is filled the primary
  // action stops being the primary action, and a page where everything shouts
  // is a page with no hierarchy. A tinted ground plus red type reads as
  // clickable at a glance and still yields to the filled button beside it.
  outline:
    "bg-honda-red-tint text-honda-red border border-honda-red/25 " +
    "hover:bg-honda-red-light hover:border-honda-red/45 hover:text-honda-red-dark " +
    "disabled:bg-cream-100 disabled:text-ink-300 disabled:border-cream-200",
  ghost:
    "bg-transparent text-honda-red hover:bg-honda-red-tint hover:text-honda-red-dark " +
    "disabled:text-ink-300",
  danger:
    "bg-danger text-white shadow-xs hover:bg-danger/90 disabled:bg-cream-200 disabled:text-ink-300",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "text-xs px-3 py-1.5 gap-1.5 rounded-md",
  md: "text-sm px-4 py-2.5 gap-2 rounded-lg",
  // A wider radius than md, to match the inputs it sits under. `lg` is only
  // used on the sign-in screen, so this cannot drift away from anything else.
  lg: "text-md px-5 py-3 gap-2 rounded-xl",
};

export const Button: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
    size?: ButtonSize;
    icon?: React.ReactNode;
    fullWidth?: boolean;
  }
> = ({
  variant = "primary",
  size = "md",
  icon,
  fullWidth,
  className = "",
  children,
  ...rest
}) => (
  <button
    className={`focus-ring inline-flex items-center justify-center font-semibold transition-[background-color,box-shadow,border-color,color] duration-150 disabled:cursor-not-allowed ${variantClasses[variant]} ${sizeClasses[size]} ${fullWidth ? "w-full" : ""} ${className}`}
    {...rest}
  >
    {icon}
    {children}
  </button>
);

/** A small square button holding only an icon. Needs a label for screen readers. */
export const IconButton: React.FC<
  React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }
> = ({ label, className = "", children, ...rest }) => (
  <button
    aria-label={label}
    title={label}
    className={`focus-ring inline-flex h-8 w-8 items-center justify-center rounded-md border border-honda-red/25 bg-honda-red-tint text-honda-red transition-colors hover:border-honda-red/45 hover:bg-honda-red-light disabled:border-cream-200 disabled:bg-cream-100 disabled:text-ink-300 ${className}`}
    {...rest}
  >
    {children}
  </button>
);

// ---------------------------------------------------------------------------

type BadgeTone = "red" | "green" | "amber" | "gray" | "wine" | "rose";

const badgeTones: Record<BadgeTone, string> = {
  red: "bg-honda-red-light text-honda-red-dark",
  green: "bg-success-light text-success",
  amber: "bg-warning-light text-warning",
  gray: "bg-cream-100 text-ink-600",
  wine: "bg-wine-100 text-wine-700",
  rose: "bg-rose-100 text-rose-500",
};

export const Badge: React.FC<{
  tone?: BadgeTone;
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}> = ({ tone = "gray", children, className = "", dot }) => (
  <span
    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-2xs font-medium uppercase tracking-[0.1em] ${badgeTones[tone]} ${className}`}
  >
    {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
    {children}
  </span>
);

// ---------------------------------------------------------------------------
// Scores
//
// One place decides what a number looks like. A score shown green in one panel
// and amber in another for the same value is the kind of thing a reviewer
// notices and stops trusting.
// ---------------------------------------------------------------------------

/**
 * What a score looks like, and — importantly — what it is called.
 *
 * `label` is not decoration. These three colours are a status scale, and a
 * status colour is never allowed to be the only thing carrying its meaning: a
 * red-green colourblind reviewer sees the amber and the red as nearly the same
 * ink, and even with full colour vision nobody is born knowing that green
 * starts at 75. The word says it; the colour reinforces it.
 *
 * `track` is the meter's unfilled remainder, a pale step of the fill's own
 * ramp rather than neutral grey, so a low score reads as a mostly-empty RED
 * bar instead of a short red mark adrift in a grey slot.
 */
export function scoreTone(score: number) {
  if (score >= 75)
    return {
      bar: "bg-success", track: "bg-success-track", text: "text-success",
      pill: "bg-success-light text-success", label: "Strong", hex: "#14724A",
    };
  if (score >= 50)
    return {
      bar: "bg-warning", track: "bg-warning-track", text: "text-warning",
      pill: "bg-warning-light text-warning", label: "Fair", hex: "#A07800",
    };
  return {
    bar: "bg-danger", track: "bg-danger-track", text: "text-danger",
    pill: "bg-danger-light text-danger", label: "Weak", hex: "#A81E14",
  };
}

export const ProgressBar: React.FC<{
  value: number;
  max?: number;
  tone?: "red" | "green" | "wine";
  className?: string;
  thick?: boolean;
}> = ({ value, max = 100, tone = "red", className = "", thick }) => {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const toneClass =
    tone === "green" ? "bg-success" : tone === "wine" ? "bg-wine-800" : "bg-honda-red";
  return (
    <div
      className={`w-full overflow-hidden rounded-full bg-cream-200 ${thick ? "h-2" : "h-1.5"} ${className}`}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={`h-full rounded-full ${toneClass} transition-all duration-500 ease-out`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
};

export const ScoreBar: React.FC<{
  label: string;
  value: number;
  className?: string;
}> = ({ label, value, className = "" }) => {
  const c = scoreTone(value);
  return (
    <div className={className}>
      {/* The number is ink, not the band colour. Values, labels and legends
          wear text tokens; the coloured bar beside them carries the state. A
          figure printed in amber on white is both harder to read and a claim
          that the number itself is a different kind of thing at 74 than at 75,
          which it is not — the scale is continuous. */}
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="label">{label}</span>
        <span className="tnum text-sm font-semibold text-ink-800">{value}%</span>
      </div>
      <div className={`h-2 w-full overflow-hidden rounded-full ${c.track}`}>
        <div
          className={`h-full rounded-full ${c.bar} transition-all duration-500 ease-out`}
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
};

export const ScoreRing: React.FC<{
  value: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  dark?: boolean;
}> = ({ value, size = 92, strokeWidth = 8, label, dark }) => {
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (Math.max(0, Math.min(100, value)) / 100) * c;
  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={dark ? "rgba(255,255,255,0.16)" : "#EDE5D6"}
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={scoreTone(value).hex}
          strokeWidth={strokeWidth}
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.6s cubic-bezier(0.16,1,0.3,1)" }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className={`tnum text-xl font-bold ${dark ? "text-white" : "text-ink-900"}`}>
          {value}%
        </span>
        {label && (
          <span className={`label mt-0.5 ${dark ? "text-white/50" : ""}`}>{label}</span>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------

export const EmptyState: React.FC<{
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}> = ({ icon, title, description, action }) => (
  <div className="flex flex-col items-center justify-center rounded-xl2 border border-dashed border-cream-300 bg-cream-50/70 px-6 py-16 text-center">
    {icon && <div className="mb-4 text-ink-300">{icon}</div>}
    <h3 className="text-md font-semibold text-ink-800">{title}</h3>
    {description && <p className="mt-1.5 max-w-sm text-sm text-ink-500">{description}</p>}
    {action && <div className="mt-6">{action}</div>}
  </div>
);

export const StatCard: React.FC<{
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  tone?: BadgeTone;
}> = ({ label, value, icon, tone = "red" }) => (
  <Card className="flex items-center gap-4">
    {icon && (
      <div
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${badgeTones[tone]}`}
      >
        {icon}
      </div>
    )}
    <div className="min-w-0">
      <div className="tnum text-2xl font-semibold text-ink-900">{value}</div>
      <div className="label mt-0.5">{label}</div>
    </div>
  </Card>
);

export const Modal: React.FC<{
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}> = ({ open, onClose, title, children, footer }) => {
  if (!open) return null;
  return (
    <div
      className="animate-in fixed inset-0 z-50 flex items-center justify-center bg-wine-900/50 px-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-xl2 bg-white p-6 shadow-pop">
        <div className="flex items-start justify-between gap-4">
          <h3 className="text-md font-semibold text-ink-900">{title}</h3>
          <IconButton label="Close" onClick={onClose} className="-mr-1 -mt-1 border-0">
            ✕
          </IconButton>
        </div>
        <div className="mt-3 text-sm text-ink-600">{children}</div>
        {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
};

export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const map: Record<string, BadgeTone> = {
    Draft: "gray",
    "Ready to Rank": "wine",
    Processing: "amber",
    Completed: "green",
    Shortlisted: "green",
    "Not shortlisted": "gray",
    Undecided: "amber",
  };
  return <Badge tone={map[status] ?? "gray"}>{status}</Badge>;
};
