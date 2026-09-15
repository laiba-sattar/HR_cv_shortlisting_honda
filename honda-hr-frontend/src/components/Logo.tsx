import React from "react";

/**
 * The Honda mark, and the owner's name.
 *
 * There is no product logo here any more, and no drawn emblem. Honda's mark is
 * a registered trademark: it is supplied as a file by the company and rendered
 * as that file, never redrawn from memory. A hand-copy is both wrong in law
 * and, more visibly, wrong in shape — the proportions of that H are exact and
 * an approximation looks like a forgery at any size above a favicon.
 *
 * Drop the official file at public/honda-logo.svg or public/honda-logo.png and
 * it appears. Both names are tried in turn, because "it did not work" almost
 * always turns out to be the other extension. Until a file exists this renders
 * the name alone — a respectable lockup, and never a bad copy of the emblem.
 *
 * Two files, because one cannot serve both grounds. The full lockup is red
 * over a black strapline: on a black header the strapline vanishes and what is
 * left looks broken. So dark surfaces get the red word alone, which needs no
 * white tile behind it and reads better for having nothing behind it.
 */

/** Light grounds: the full lockup, red word over the black strapline. */
const ON_LIGHT = ["/honda-logo.svg", "/honda-logo.png"];
/** Dark grounds: the red word alone. */
const ON_DARK = ["/honda-logo-on-dark.svg", "/honda-logo-on-dark.png", ...ON_LIGHT];
/** The full corporate lockup, tagline and all. Wide — give it room. */
const FULL = ["/honda-lockup.svg", "/honda-lockup.png", ...ON_LIGHT];

const Mark: React.FC<{ tone: "dark" | "light"; size: number; full?: boolean }> = ({
  tone,
  size,
  full,
}) => {
  const sources = full ? FULL : tone === "light" ? ON_DARK : ON_LIGHT;
  // Walk the candidates; give up quietly when none of them load.
  const [attempt, setAttempt] = React.useState(0);
  if (attempt >= sources.length) return null;

  return (
    <img
      key={sources[attempt]}
      src={sources[attempt]}
      alt="Honda"
      onError={() => setAttempt((n) => n + 1)}
      style={{ height: size, width: "auto" }}
      className="block shrink-0 object-contain"
    />
  );
};

const Logo: React.FC<{
  compact?: boolean;
  /** "light" = on a black surface, "dark" = on a grey or white one. */
  tone?: "dark" | "light";
  size?: number;
  className?: string;
  /** The wide corporate lockup with the tagline, for a page that has room. */
  full?: boolean;
  /**
   * The line under the name. Pass null where the page already says it — on the
   * sign-in screen the heading names the system, and printing the same words
   * twice a centimetre apart reads as a mistake rather than as emphasis.
   */
  sub?: string | null;
}> = ({ compact, tone = "dark", size = 22, className = "", sub = "Recruitment", full }) => (
  <div className={`flex items-center gap-3 ${className}`}>
    <Mark tone={tone} size={size} full={full} />
    {!compact && (
      <div className="leading-none">
        <div
          className={`text-[15px] font-semibold tracking-[-0.01em] ${
            tone === "light" ? "text-white" : "text-ink-900"
          }`}
        >
          Honda Atlas Cars
        </div>
        {sub && (
          <div
            className={`mt-[3px] font-mono text-[9px] font-medium uppercase tracking-[0.15em] ${
              tone === "light" ? "text-wine-300" : "text-ink-400"
            }`}
          >
            {sub}
          </div>
        )}
      </div>
    )}
  </div>
);

export default Logo;
