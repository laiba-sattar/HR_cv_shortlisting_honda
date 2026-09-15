/** @type {import('tailwindcss').Config} */

/**
 * The design system.
 *
 * White, red and black — Honda's own three — with the page sitting between
 * the extremes rather than at one of them. A pure-white page under a dense
 * table glares after an hour; a dark one makes small figures swim. The ground
 * here is a light steel grey and the cards on it are white, so the content is
 * the brightest thing on screen and the eye goes there first.
 *
 * Three families, each with one job:
 *
 *   wine    kept as a name, now black. The header band and any dark panel.
 *           It carries the brand weight so the working surfaces stay quiet.
 *   cream   kept as a name, now steel grey. The page, its fills and borders.
 *   red     Honda's red, reserved for action and emphasis. Used sparingly:
 *           when everything is emphasised nothing is.
 *
 * The colour NAMES did not change when the scheme did. That is deliberate —
 * every page already says bg-cream-50 or bg-wine-800, and renaming them would
 * have meant touching a dozen files to achieve exactly nothing. The names are
 * roles; the hexes are the theme.
 *
 * Neutrals are very slightly cool. Against Honda's red a warm grey looks
 * muddy, where a cool one reads as metal.
 */

/**
 * The design system.
 *
 * Three families, each with one job:
 *
 *   wine    the deep burgundy. Header, footers, dark panels — it carries the
 *           brand weight so the working surfaces can stay quiet.
 *   cream   the page. Warm rather than grey, which is what keeps a dense
 *           table-and-form tool from reading as a spreadsheet.
 *   red     Honda's own red, reserved for action and emphasis. Used sparingly:
 *           when everything is emphasised nothing is.
 *
 * Neutrals are warm-biased on purpose. A pure grey next to cream looks like a
 * mistake; these carry a trace of the wine hue so the page reads as one set.
 */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Archivo", "-apple-system", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SF Mono", "Consolas", "monospace"],
      },

      colors: {
        // Black. Header, footers, dark panels.
        wine: {
          900: "#08090A",
          800: "#15171A",   // the header band
          700: "#1F2226",
          600: "#2A2E33",
          500: "#3A3F46",
          300: "#98A0A9",   // muted text ON black
          100: "#EAECEF",   // pale tint for badges on light
        },

        // The page. Steel rather than paper — this is the "middle".
        cream: {
          50: "#EFF1F3",    // page ground
          100: "#E5E8EC",   // subtle fill, hover
          200: "#D7DBE0",   // borders
          300: "#C2C8CF",   // stronger borders
        },

        // Honda red — two of them, and they are not interchangeable.
        //
        // `red` is #8C1A1E, sampled out of the campaign banner ("Rs. 200,000")
        // rather than estimated: a deep maroon-red that Honda's own marketing
        // uses on photography. It is the base of this interface.
        //
        // `red-bright` is #CC0000, sampled out of the logo file itself. The
        // mark is printed in that value and nothing else may sit next to it
        // claiming to be the same colour.
        //
        // The two agree because they are the same hue — 358° and 360°, a two
        // degree difference nobody can see. Only the depth differs, so they
        // read as one colour at two weights rather than as two reds arguing.
        // (The crimson that sat here before was 340° — that one really did
        // fight the mark, and looked faintly pink beside it.)
        //
        // The 700/800/900 steps carry the sign-in panel's gradient down into
        // black; the first three are the interface's action colour.
        honda: {
          red: "#8C1A1E",
          "red-bright": "#CC0000",
          "red-dark": "#77161A",
          "red-darker": "#621215",
          "red-light": "#F6EAEA",
          "red-tint": "#FCF6F6",
          "red-700": "#4D0E11",
          "red-800": "#31090B",
          "red-900": "#160405",
        },

        // Warm off-white, for type on the red panel. Pure white on this red
        // is faintly harsh and makes the panel look like a warning.
        bone: "#F7F2F0",

        rose: {
          500: "#B31237",
          400: "#CE3355",
          100: "#FAE3E9",
        },

        // Text and hairlines. Cool-neutral.
        ink: {
          900: "#0E1013",
          800: "#191C20",
          700: "#2A2E34",
          600: "#454A52",
          500: "#5F656E",
          400: "#838A93",
          300: "#A8AEB7",
          200: "#CBD0D6",
          100: "#E2E5E9",
          50: "#F2F4F6",
        },

        // The three score bands. These are status colours, not a palette of
        // series, and they were re-stepped rather than chosen by eye.
        //
        // The old amber #96620F and red #B3261E measured ΔE 3.4 apart under
        // deuteranopia and only 12.9 apart with full colour vision — that is,
        // most people could not reliably tell a "fair" bar from a "weak" one,
        // and a red-green colourblind reader had no chance at all. Since the
        // band was carried by colour and nothing else, that made two thirds of
        // the scale unreadable.
        //
        // This triple passes every check: worst adjacent pair ΔE 8.7 under
        // protanopia, 17.4 with normal vision, all three above 3:1 on white.
        // A band label ships beside the colour regardless — a status colour is
        // never allowed to be the only thing saying what it means.
        //
        // `track` is the meter's unfilled remainder: a lighter step of the
        // fill's OWN ramp, so the whole bar reads as one state rather than as
        // a coloured fill sitting in a neutral grey slot.
        success: { DEFAULT: "#14724A", light: "#E3F1EA", track: "#C2E1D0" },
        warning: { DEFAULT: "#A07800", light: "#F8F1DA", track: "#EBDCA1" },
        danger: { DEFAULT: "#A81E14", light: "#FAE8E6", track: "#F1C6C1" },
      },

      fontSize: {
        // A tighter scale than the default, because this is a working tool:
        // information density matters more than generous display sizes.
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.06em" }],
        xs: ["0.75rem", { lineHeight: "1.1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.875rem", { lineHeight: "1.45rem" }],
        md: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1.0625rem", { lineHeight: "1.5rem" }],
        xl: ["1.25rem", { lineHeight: "1.65rem", letterSpacing: "-0.01em" }],
        "2xl": ["1.5rem", { lineHeight: "1.9rem", letterSpacing: "-0.015em" }],
        "3xl": ["1.875rem", { lineHeight: "2.25rem", letterSpacing: "-0.02em" }],
        "4xl": ["2.375rem", { lineHeight: "2.6rem", letterSpacing: "-0.025em" }],
        "5xl": ["3rem", { lineHeight: "3.1rem", letterSpacing: "-0.03em" }],
      },

      boxShadow: {
        // Neutral and close. On a grey ground a white card needs only a
        // whisper of shadow to lift; anything more and it starts to float.
        xs: "0 1px 2px rgba(14,16,19,0.06)",
        card: "0 1px 2px rgba(14,16,19,0.05), 0 2px 10px rgba(14,16,19,0.06)",
        raised: "0 2px 4px rgba(14,16,19,0.06), 0 8px 24px rgba(14,16,19,0.08)",
        pop: "0 12px 36px rgba(14,16,19,0.18)",
        "inner-line": "inset 0 -1px 0 rgba(14,16,19,0.08)",
      },

      borderRadius: {
        xl2: "0.875rem",
        xl3: "1.25rem",
      },

      maxWidth: {
        shell: "1560px",
      },
    },
  },
  plugins: [],
};
