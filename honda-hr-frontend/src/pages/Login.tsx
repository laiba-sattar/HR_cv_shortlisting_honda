import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Loader2, ShieldCheck } from "lucide-react";
import Logo from "../components/Logo";
import { Button } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import {
  firebaseConfigured,
  googleErrorMessage,
  passwordErrorMessage,
  resendVerification,
  sendPasswordReset,
  signInWithGoogle,
  signInWithPassword,
  signUpWithPassword,
} from "../firebase";
import * as api from "../api";

/**
 * Landing page, sign-up and sign-in.
 *
 * Nobody creates an account here. The four addresses that may use this system
 * are set by an administrator, so "Sign up" means "set your password for the
 * first time" — the account already exists, it just has no password yet.
 *
 * Which of the two forms opens first is a guess, and it has to be: the page
 * cannot know whether somebody is new until they have typed an address. So it
 * remembers, per browser, whether a sign-in has ever succeeded here. A fresh
 * browser opens on Sign up; one that has been used before opens on Sign in.
 * Both carry a link to the other, so a wrong guess costs one click.
 *
 * The guess can also be overruled by the address: /signup and /signin each
 * force their own form, so a link handed to somebody who has never been here
 * lands on the right one regardless of what their browser remembers. /login
 * leaves the decision to the guess.
 *
 * Sign-up and forgotten-password are the same operation underneath — set a
 * password, prove the address by email — so they share one form and differ
 * only in what they are called.
 */

const RESEND_SECONDS = 60;


/** Per-browser memory of "somebody has signed in here before". */
const RETURNING_KEY = "caliper.returning";

const hasSignedInBefore = (): boolean => {
  // Private windows and locked-down browsers throw on access rather than
  // returning nothing, so this cannot be a bare read.
  try {
    return localStorage.getItem(RETURNING_KEY) === "1";
  } catch {
    return false;
  }
};

const rememberSignedIn = (): void => {
  try {
    localStorage.setItem(RETURNING_KEY, "1");
  } catch {
    /* Not worth surfacing: the cost is opening on the wrong form once. */
  }
};

type Step = "signin" | "setup" | "verify" | "reset-sent";
/** What the shared password form is being used for. */
type SetupReason = "signup" | "forgot";

const Login: React.FC = () => {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { user, ready, options, setUser } = useAuth();

  const [step, setStep] = useState<Step>(() => {
    if (pathname === "/signup") return "setup";
    if (pathname === "/signin") return "signin";
    return hasSignedInBefore() ? "signin" : "setup";
  });
  const [setupReason, setSetupReason] = useState<SetupReason>("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);


  // One component serves /login, /signup and /signin, so moving between those
  // addresses changes the route without remounting and the initial state above
  // never runs again. Follow the address whenever it names a form.
  useEffect(() => {
    if (pathname === "/signup") {
      setStep("setup");
      setSetupReason("signup");
    } else if (pathname === "/signin") {
      setStep("signin");
    } else {
      setStep(hasSignedInBefore() ? "signin" : "setup");
      setSetupReason("signup");
    }
  }, [pathname]);

  // Already signed in — don't make them do it again.
  useEffect(() => {
    if (ready && user) navigate("/", { replace: true });
  }, [ready, user, navigate]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const done = (signedIn: api.SignedInUser) => {
    rememberSignedIn();
    setUser(signedIn);
    navigate("/", { replace: true });
  };

  const goto = (next: Step, reason?: SetupReason) => {
    setStep(next);
    if (reason) setSetupReason(reason);
    setError(null);
    setPassword("");
    setConfirm("");
  };

  // --- Google ---------------------------------------------------------------
  //
  // The shortest route: Google proves the mailbox in one click and the server
  // puts that address to the same allowlist everything else is checked
  // against. Being able to sign into Google has never been permission here.
  const continueWithGoogle = async () => {
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const token = await signInWithGoogle();
      done(await api.signInWithFirebaseEmail(token));
    } catch (err) {
      // A closed pop-up returns an empty message: the person shut it
      // themselves and does not need to be told what they just did.
      const message = googleErrorMessage(err);
      if (message) setError(message);
    } finally {
      setBusy(false);
    }
  };

  // --- sign in ---------------------------------------------------------
  //
  // Firebase checks the password; this server never sees one. What comes back
  // is a signed token naming a CONFIRMED address, and the server then asks the
  // only question it asks of anybody: is that address on the list?
  const submitSignIn = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const token = await signInWithPassword(email.trim(), password);
      done(await api.signInWithFirebaseEmail(token));
    } catch (err) {
      setError(passwordErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  // --- sign up: choose a password ------------------------------------------
  //
  // Firebase creates the account and emails the confirmation link itself. The
  // confirmation is not a formality: Firebase lets anybody register any
  // address, so without it a stranger could sign up as a colleague and the
  // allowlist would pass them — the address really is listed.
  const submitSetup = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (busy) return;
    if (password !== confirm) {
      setError("The two passwords do not match.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await signUpWithPassword(email.trim(), password);
      setStep("verify");
      setCooldown(RESEND_SECONDS);
    } catch (err) {
      setError(passwordErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  // --- forgotten password ---------------------------------------------------
  //
  // Firebase sends this one too, which is what makes it work at all: our own
  // mail provider will not deliver to anybody but the account holder.
  const submitForgot = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (busy) return;
    if (!email.trim()) {
      setError("Enter your work email first.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await sendPasswordReset(email.trim());
      setStep("reset-sent");
      setCooldown(RESEND_SECONDS);
    } catch (err) {
      setError(passwordErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setError(null);
    setBusy(true);
    try {
      if (step === "reset-sent") await sendPasswordReset(email.trim());
      else await resendVerification(email.trim(), password);
      setCooldown(RESEND_SECONDS);
    } catch (err) {
      setError(passwordErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };


  const signingUp = setupReason === "signup";

  return (
    // Red panel left, form right. Only the logo moved across — the panel came
    // back. On a phone the two halves stack in source order, so branding lands
    // above the form either way.
    <div className="flex min-h-screen flex-col lg:flex-row">
      {/* ---- the telling half ----
          Honda's own red, not black and not paper. Black read as somebody
          else's product; white read as unfinished. A saturated red panel
          against a white one gives the screen a centre of gravity without
          either half being heavy.

          The gradient runs light-to-deep across the diagonal and lands in
          near-black at the far corner. A flat fill of this red looks like a
          warning banner; the movement is what makes it read as a surface, and
          the dark corner is what stops it reading as flat paint.

          The light sits at the outer edge of the screen and the dark at the
          seam with the form. Those origins follow the panel: light falling
          toward the middle of a page looks like a mistake, so moving this
          panel without moving them is exactly how that happens. */}
      {/* `lg:pt-[20vh]`: the heading starts a fifth of the way down the panel.
          vh rather than a percentage because at this width the panel is the
          full height of the window, so 20vh IS 20% of the red — and unlike a
          percentage it does not have to be measured against a padding box that
          is already 64px shorter than the thing being divided.

          Split from the bottom padding on purpose. `py-16` would have put the
          same figure at both ends, and the space wanted here is only at the
          top; the bottom already holds the footer note. */}
      <div className="relative flex flex-col overflow-hidden bg-honda-red px-8 py-12 lg:w-[52%] lg:px-16 lg:pb-16 lg:pt-[20vh]">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(156deg, #A82026 0%, #8C1A1E 27%, #701317 56%, #3A0A0C 81%, #120405 100%)",
          }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              // The top-left glow is the logo's own #CC0000, diffused. On this
              // deeper base it lifts that corner to exactly the red the mark
              // is printed in, so the two values read as one light source
              // rather than as a mismatch. The old glow was a pale pink and
              // did no such work.
              "radial-gradient(760px 470px at 4% -10%, rgba(204,0,0,0.58) 0%, transparent 62%)," +
              "radial-gradient(320px 240px at 8% -4%, rgba(255,150,130,0.20) 0%, transparent 66%)," +
              "radial-gradient(640px 520px at 106% 104%, rgba(6,3,4,0.80) 0%, transparent 62%)," +
              "radial-gradient(420px 320px at 96% 4%, rgba(6,3,4,0.34) 0%, transparent 64%)",
          }}
        />
        {/* A fine grid, barely there. On a plain gradient the eye finds
            nothing to hold; this gives it a texture without a pattern. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.35]"
          style={{
            backgroundImage: "radial-gradient(rgba(255,255,255,0.22) 1px, transparent 1px)",
            backgroundSize: "24px 24px",
            maskImage: "radial-gradient(700px 460px at 22% 34%, #000 0%, transparent 78%)",
            WebkitMaskImage: "radial-gradient(700px 460px at 22% 34%, #000 0%, transparent 78%)",
          }}
        />

        {/* Every line below is checked against the company's own About page.
            A sign-in screen is the first thing a supervisor sees, and a wrong
            date on it costs more trust than an empty panel ever would.

            `justify-start`, not centre. With the line above the heading gone
            there is nothing left to balance against, and centring what remains
            just splits the empty space in two and puts half of it at the top.
            Starting at the top leaves the whole of it below the tiles, where
            the footer note is already sitting in it. */}
        <div className="relative flex flex-1 flex-col justify-start">
          <h1 className="max-w-[15ch] text-4xl font-semibold leading-[1.08] tracking-[-0.03em] text-bone lg:text-[3.25rem]">
            Built for the people who build the cars.
          </h1>

          <p className="mt-6 max-w-[46ch] text-md leading-relaxed text-bone/75">
            A joint venture between Honda Motor Company, Japan and the Atlas
            Group. Cars have come off the Manga Mandi line since 1994.
          </p>

          {/* Hairlines between the tiles, not around them: the divider is a
              1px gap that lets the dark fill below show through, so the group
              reads as one object cut into three rather than three boxes. */}
          <dl className="mt-11 grid max-w-md gap-px overflow-hidden rounded-xl2 bg-white/10 ring-1 ring-inset ring-white/10 sm:grid-cols-3">
            {[
              ["1994", "First car built"],
              ["Lahore", "Manga Mandi plant"],
              ["HR", "Internal tool"],
            ].map(([term, detail]) => (
              // Dark, not light. A white wash over red turns pink, which is the
              // one thing this palette must not do — and it flattened the tiles
              // into the panel besides. Deepening instead of lifting keeps them
              // in the red family and gives the group an actual edge.
              <div key={term} className="bg-honda-red-900/65 px-4 py-3.5 backdrop-blur-[3px]">
                <dt className="font-mono text-sm font-semibold tracking-[-0.01em] text-bone">
                  {term}
                </dt>
                <dd className="mt-1 text-xs leading-snug text-bone/65">{detail}</dd>
              </div>
            ))}
          </dl>
        </div>

        <p className="relative mt-14 flex items-start gap-2 text-2xs leading-relaxed text-bone/60 lg:mt-0">
          <ShieldCheck size={13} className="mt-px shrink-0 text-bone/80" />
          Decision support. The system ranks and explains; a person makes the
          hiring decision.
        </p>
      </div>

      {/* ---- the working half ----
          Not flat white. A white card on a white page has no edge and no
          weight — it reads as a form printed on the wall rather than as an
          object. The faintest wash to grey behind it is what lets the card
          be the brightest thing on this side, which is where the eye should
          land the moment the page opens. */}
      <div
        className="relative flex flex-1 flex-col bg-cream-50"
        style={{
          backgroundImage:
            "radial-gradient(900px 620px at 62% 34%, #FFFFFF 0%, rgba(255,255,255,0) 72%)",
        }}
      >
      {options?.open_access && (
        <div className="relative flex items-center justify-center gap-2 bg-warning px-4 py-2 text-center text-xs font-semibold text-ink-900">
          <AlertTriangle size={14} className="shrink-0" />
          Open access is on. Anyone can sign in, so do not upload real candidate CVs.
        </div>
      )}

        {/* The lockup, in the corner rather than over the card.
            No plate, and that is the point of having moved it off the red: the
            mark is red type above a black strapline, which is what a light
            ground is for. It sits in the flow rather than absolutely placed,
            so it can never land on top of the card on a short screen.

            The card below stays centred in whatever height is left, which is
            why this is a sibling of that block and not inside it. */}
        <div className="relative shrink-0 px-6 pt-8 sm:px-10 sm:pt-10">
          <Logo full size={28} compact />
        </div>

        <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 sm:px-10">
          <div className="w-full max-w-[400px]">
          {/* ---- the card ----
              A red hairline along the top edge, three pixels of colour that
              carry the mark above it down onto the card — without which the
              logo floats and the card below it belongs to nobody.
              The shadow is wide and very soft rather than tight and dark —
              a close shadow makes a card look stuck on, a diffuse one makes
              it look lifted. */}
          <div className="animate-in relative overflow-hidden rounded-[1.375rem] bg-white p-7 shadow-[0_0_0_1px_rgba(14,16,19,0.06),0_1px_2px_rgba(14,16,19,0.04),0_18px_50px_-18px_rgba(14,16,19,0.22)] sm:p-9">
            {/* The outline is a shadow ring, not a border. A real border sits
                outside the padding box, so this bar landed one pixel below it
                with a hairline of grey above — which read as a stray line
                rather than as the card's own edge. */}
            <span
              aria-hidden
              className="absolute inset-x-0 top-0 h-[3px]"
              style={{
                background:
                  "linear-gradient(90deg, #CC0000 0%, #8C1A1E 46%, rgba(140,26,30,0) 100%)",
              }}
            />
            {(step === "verify" || step === "reset-sent") && (
              <BackLink label="Back to sign in" onClick={() => goto("signin")} />
            )}

            {/* ---- sign in ---- */}
            {step === "signin" && (
              <form onSubmit={submitSignIn}>
                <h2 className="text-2xl font-semibold tracking-[-0.02em] text-ink-900">
                  Sign in
                </h2>

                <Field label="Work email" htmlFor="email">
                  <input
                    id="email"
                    type="email"
                    required
                    autoFocus
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@company.com"
                    className={inputClass}
                  />
                </Field>

                <Field label="Password" htmlFor="password">
                  <input
                    id="password"
                    type="password"
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={inputClass}
                  />
                </Field>

                {error && <ErrorNote text={error} />}

                <Button
                  type="submit"
                  fullWidth
                  size="lg"
                  className="mt-5"
                  disabled={busy || !email.trim() || !password}
                  icon={busy ? <Spinner /> : undefined}
                >
                  {busy ? "Signing in…" : "Sign in"}
                </Button>

                {/* Only offered when the server has Firebase credentials AND
                    this build has the web config. Showing a route that cannot
                    work is worse than not showing it. */}
                {options?.firebase_email && firebaseConfigured() && (
                  <>
                    <Divider />
                    <button
                      type="button"
                      onClick={continueWithGoogle}
                      disabled={busy}
                      className="focus-ring flex w-full items-center justify-center gap-2.5 rounded-xl border border-cream-200 bg-white py-3 text-sm font-semibold text-ink-800 shadow-xs transition-colors hover:border-cream-300 hover:bg-cream-50 disabled:cursor-not-allowed disabled:text-ink-300"
                    >
                      <GoogleMark />
                      Continue with Google
                    </button>
                  </>
                )}

                <div className="mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <Quiet onClick={() => goto("setup", "signup")}>
                    First time here? Sign up
                  </Quiet>
                  {/* Firebase emails the reset link, so there is nothing to
                      fill in first — the address is already in the box above. */}
                  <Quiet onClick={submitForgot}>Forgot password?</Quiet>
                </div>
              </form>
            )}

            {/* ---- sign up / reset: the same operation, named differently ---- */}
            {step === "setup" && (
              <form onSubmit={submitSetup}>
                <h2 className="text-xl font-semibold text-ink-900">
                  Sign up
                </h2>
                <p className="mt-1.5 text-sm text-ink-500">
                  Choose a password. Google will email you a link to confirm the
                  address before you can sign in.
                </p>

                <Field label="Work email" htmlFor="setup-email">
                  <input
                    id="setup-email"
                    type="email"
                    required
                    autoFocus
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@company.com"
                    className={inputClass}
                  />
                </Field>

                <Field
                  label={signingUp ? "Password" : "New password"}
                  htmlFor="new-password"
                >
                  <input
                    id="new-password"
                    type="password"
                    required
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="at least 10 characters"
                    className={inputClass}
                  />
                </Field>

                <Field label="Type it again" htmlFor="confirm-password">
                  <input
                    id="confirm-password"
                    type="password"
                    required
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className={inputClass}
                  />
                </Field>

                {error && <ErrorNote text={error} />}

                <Button
                  type="submit"
                  fullWidth
                  size="lg"
                  className="mt-5"
                  disabled={busy || !email.trim() || password.length < 10 || !confirm}
                  icon={busy ? <Spinner /> : undefined}
                >
                  {busy ? "Sending…" : signingUp ? "Sign up" : "Continue"}
                </Button>

                {/* Google belongs on THIS form more than on the other one.
                    A first-timer has no password, and the form above emails a
                    code to confirm the address — the exact step that cannot be
                    relied on. Google confirms the same address in one click and
                    needs no email at all, so leaving it off the sign-up form
                    hid it from the people who need it most. */}
                {options?.firebase_email && firebaseConfigured() && (
                  <>
                    <Divider />
                    <button
                      type="button"
                      onClick={continueWithGoogle}
                      disabled={busy}
                      className="focus-ring flex w-full items-center justify-center gap-2.5 rounded-xl border border-cream-200 bg-white py-3 text-sm font-semibold text-ink-800 shadow-xs transition-colors hover:border-cream-300 hover:bg-cream-50 disabled:cursor-not-allowed disabled:text-ink-300"
                    >
                      <GoogleMark />
                      Continue with Google
                    </button>
                    {/* Was "you can set a password later from Help". That
                        panel is gone — the password lives in Firebase now, so
                        the only way to get one is Sign up or Forgot password.
                        Leaving the old line would send people to a page that
                        no longer has the box it names. */}
                    <p className="mt-2 text-center text-xs leading-relaxed text-ink-500">
                      No password to choose, and nothing to confirm by email.
                    </p>
                  </>
                )}

                <div className="mt-5">
                  <Quiet onClick={() => goto("signin")}>
                    Already have a password? Sign in
                  </Quiet>
                </div>
              </form>
            )}

            {/* ---- confirm the address, or reset the password ----
                Both are the same screen: Firebase has emailed a link, and the
                only thing left to do is open it. There is no code to type,
                because Firebase does not issue one — a box asking for six
                digits that will never arrive would be worse than no box. */}
            {(step === "verify" || step === "reset-sent") && (
              <div>
                <h2 className="text-2xl font-semibold tracking-[-0.02em] text-ink-900">
                  Check your email
                </h2>
                <p className="mt-2 break-words text-sm leading-relaxed text-ink-600">
                  {step === "verify"
                    ? "Your account is created. Open the link we sent to "
                    : "A link to choose a new password is on its way to "}
                  <span className="font-semibold text-ink-900">{email.trim()}</span>
                  {step === "verify"
                    ? " to confirm the address, then come back and sign in."
                    : ". Open it, set the password, then come back and sign in."}
                </p>
                <p className="mt-3 text-xs leading-relaxed text-ink-500">
                  Nothing after a minute or two? Check the spam folder before
                  asking for another.
                </p>

                {error && <ErrorNote text={error} />}

                <Button
                  fullWidth
                  size="lg"
                  variant="outline"
                  className="mt-5"
                  disabled={busy || cooldown > 0}
                  onClick={resend}
                >
                  {cooldown > 0 ? `Send another in ${cooldown}s` : "Send it again"}
                </Button>
                {/* No second "Back to sign in" here: the arrow at the top of
                    the card already is one, and two identical links on a card
                    this short read as two different destinations. */}
              </div>
            )}
          </div>

          <p className="mt-5 text-center text-xs leading-relaxed text-ink-400">
            Authorised HR staff only. If your address is not recognised, ask an
            administrator to add it.
          </p>
          </div>
        </div>
      </div>
    </div>
  );
};

// The standard control, restyled for this one screen. `.field` still supplies
// the metrics and the behaviour — the overrides here are only appearance, so
// the two inputs cannot drift apart the way two hand-written class strings do.
//
// Two changes, both doing real work. The resting state is a soft grey inset
// rather than a white box on a white card, where the border was the only thing
// saying "type here"; on focus it turns white and lifts, so the field being
// edited is the one bright rectangle on the screen. And the focus ring is a
// wide soft halo at 10% instead of a hard 1px line, which is what stops a
// focused field looking like a validation error.
const inputClass =
  "field rounded-xl border-cream-200 bg-cream-50/70 py-3 " +
  "hover:border-cream-300 hover:bg-cream-50 " +
  "focus:border-honda-red/70 focus:bg-white focus:ring-4 focus:ring-honda-red/10";

const Field: React.FC<{ label: string; htmlFor: string; children: React.ReactNode }> = ({
  label,
  htmlFor,
  children,
}) => (
  <>
    <label
      htmlFor={htmlFor}
      className="mt-5 block font-mono text-2xs font-medium uppercase tracking-[0.14em] text-ink-500"
    >
      {label}
    </label>
    <div className="mt-1.5">{children}</div>
  </>
);

/**
 * Google's own mark, inline.
 *
 * Drawn as the four brand colours because that is what Google's branding
 * rules require on a "Continue with Google" button, and because a grey G
 * next to a red one reads as a generic icon rather than as Google.
 */
const GoogleMark: React.FC = () => (
  <svg aria-hidden viewBox="0 0 24 24" className="h-[18px] w-[18px] shrink-0">
    <path
      fill="#4285F4"
      d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.63h6.46a5.52 5.52 0 0 1-2.4 3.62v3h3.88c2.27-2.09 3.58-5.17 3.58-8.8Z"
    />
    <path
      fill="#34A853"
      d="M12 24c3.24 0 5.96-1.08 7.94-2.91l-3.88-3.01c-1.08.72-2.45 1.15-4.06 1.15-3.13 0-5.78-2.11-6.73-4.95H1.26v3.1A12 12 0 0 0 12 24Z"
    />
    <path
      fill="#FBBC05"
      d="M5.27 14.28a7.2 7.2 0 0 1 0-4.56v-3.1H1.26a12 12 0 0 0 0 10.76l4.01-3.1Z"
    />
    <path
      fill="#EA4335"
      d="M12 4.77c1.77 0 3.35.61 4.6 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0A12 12 0 0 0 1.26 6.62l4.01 3.1C6.22 6.88 8.87 4.77 12 4.77Z"
    />
  </svg>
);

const Spinner: React.FC = () => <Loader2 size={17} className="animate-spin" />;

/**
 * "or", between two ways of doing the same thing.
 *
 * The word alone, with no rules either side of it. The rules were the last
 * two lines on this screen that could be mistaken for dashes, and the word
 * with air around it separates the two routes perfectly well without them.
 */
const Divider: React.FC = () => (
  <p
    className="my-4 text-center font-mono text-2xs uppercase tracking-[0.14em] text-ink-400"
    aria-hidden
  >
    or
  </p>
);

/** A secondary action that must not compete with the primary button. */
const Quiet: React.FC<{ onClick: () => void; children: React.ReactNode }> = ({
  onClick,
  children,
}) => (
  <button
    type="button"
    onClick={onClick}
    className="focus-ring rounded text-sm font-medium text-ink-500 underline decoration-ink-300 underline-offset-4 transition-colors hover:text-ink-900 hover:decoration-ink-500"
  >
    {children}
  </button>
);

const BackLink: React.FC<{ onClick: () => void; label: string }> = ({
  onClick,
  label,
}) => (
  <button
    type="button"
    onClick={onClick}
    className="focus-ring -ml-1 mb-5 inline-flex items-center gap-1.5 rounded px-1 py-0.5 text-sm font-medium text-ink-500 transition-colors hover:text-ink-900"
  >
    <ArrowLeft size={14} /> {label}
  </button>
);

const ErrorNote: React.FC<{ text: string }> = ({ text }) => (
  <div
    role="alert"
    className="mt-4 flex items-start gap-2 rounded-lg border border-honda-red/25 bg-honda-red-tint px-3.5 py-2.5 text-sm font-medium leading-relaxed text-honda-red-darker"
  >
    <AlertTriangle size={14} className="mt-0.5 shrink-0" />
    <span>{text}</span>
  </div>
);

export default Login;
