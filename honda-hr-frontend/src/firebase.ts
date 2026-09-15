/**
 * Sign-in, through Firebase. Two routes: Google, and email + password.
 *
 * Firebase holds the passwords and sends the emails — the confirmation link,
 * the reset link. Our own server holds none of that. The reason is not tidiness
 * but delivery: sending mail ourselves needs a provider that will write to an
 * arbitrary recipient, and the free tier of the one configured refuses every
 * address except the account holder's until a domain is verified, which needs a
 * domain nobody here owns. Firebase sends from its own infrastructure, to
 * anyone, at no cost.
 *
 * What Firebase decides is one question only: does this person control this
 * mailbox. Whether that mailbox may see a candidate's CV is decided by our own
 * server, against the allowed-users list. A verified address has never been
 * permission here and must not become it.
 *
 * The SDK is loaded from Google's CDN at the moment it is first needed, rather
 * than installed as an npm dependency. Two reasons, in order of importance:
 *
 *   1. Nothing is lost by it. Firebase sign-in already cannot work offline —
 *      the browser has to talk to Google's identity servers either way.
 *      Fetching the SDK from the same origin adds no dependency that was not
 *      already there.
 *   2. The npm package is `firebase`, an umbrella over a dozen products we do
 *      not use, and its deeply nested paths were failing to install on
 *      Windows. Not shipping it also keeps the build reproducible on a machine
 *      where that install refuses to complete.
 *
 * The trade is that a typo in an export name becomes a runtime error rather
 * than a compile error, since a URL import carries no types. The surface used
 * here is a handful of functions wide and pinned to one SDK version, which is a
 * small enough target to be worth it.
 *
 * The config values below are not secrets. A Firebase web config ships inside
 * every page that uses it and is visible to anyone; what protects the project
 * is the authorised-domains list in the console, plus the fact that our server
 * checks the list. The service-account key, which IS a secret, lives only on
 * the server and never reaches this file.
 */

/** Pinned deliberately: "latest" would let Google change our app underneath us. */
const SDK_VERSION = "12.18.0";
const CDN = `https://www.gstatic.com/firebasejs/${SDK_VERSION}`;

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

/** Whether this build has enough configuration to attempt Firebase sign-in. */
export const firebaseConfigured = (): boolean =>
  Boolean(config.apiKey && config.authDomain && config.projectId && config.appId);

/* eslint-disable @typescript-eslint/no-explicit-any */
type Sdk = { app: any; auth: any };

let loading: Promise<Sdk> | null = null;

/**
 * Fetch the two SDK modules, once per page load.
 *
 * A failed load is deliberately not cached: the usual cause is a dropped
 * connection, and a second attempt a moment later should be allowed to
 * succeed rather than replaying the first failure forever.
 */
function loadSdk(): Promise<Sdk> {
  if (!loading) {
    loading = Promise.all([
      import(/* @vite-ignore */ `${CDN}/firebase-app.js`),
      import(/* @vite-ignore */ `${CDN}/firebase-auth.js`),
    ])
      .then(([app, auth]) => ({ app, auth }))
      .catch((e) => {
        loading = null;
        throw new SdkUnavailable(String(e));
      });
  }
  return loading;
}

/** The SDK itself could not be fetched — distinct from Firebase refusing us. */
class SdkUnavailable extends Error {
  readonly code = "sdk/unavailable";
}

/* ---------------------------------------------------------------------------
 * Google sign-in
 *
 * The shorter of the two routes: no password to remember, no link to find.
 * Most of the people on the list already hold the Google account for the
 * address they were added under, so one click is the whole flow.
 *
 * It is not a second front door. Google proves the mailbox — exactly what the
 * confirmation email proves — and the server then puts that address to the
 * same allowed-users list. Somebody with a Google account and no place on that
 * list gets the same refusal they would get anywhere else.
 * ------------------------------------------------------------------------ */

/** Sign in with Google and return the Firebase ID token for our server. */
export async function signInWithGoogle(): Promise<string> {
  const sdk = await loadSdk();
  const { initializeApp, getApps } = sdk.app;
  const { getAuth, GoogleAuthProvider, signInWithPopup, signOut } = sdk.auth;

  const app = getApps().length ? getApps()[0] : initializeApp(config);
  const auth = getAuth(app);
  auth.useDeviceLanguage();

  const provider = new GoogleAuthProvider();
  // Always ask which account. Without this, somebody already signed into a
  // personal Google account in this browser is silently signed in as that
  // one — and then refused, with no clue that the wrong account was used.
  provider.setCustomParameters({ prompt: "select_account" });

  const credential = await signInWithPopup(auth, provider);
  const token = await credential.user.getIdToken();
  // We have what we need. Firebase's own session is not ours.
  await signOut(auth).catch(() => undefined);
  return token;
}

/** Turn a Google sign-in failure into something worth showing a person. */
export function googleErrorMessage(err: unknown): string {
  const code = (err as { code?: string })?.code ?? "";
  switch (code) {
    case "sdk/unavailable":
      return "Could not reach Google to start sign-in. Check the connection and try again.";
    case "auth/popup-blocked":
      return "Your browser blocked the Google window. Allow pop-ups for this site, then try again.";
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request":
      // Not an error worth alarming anybody about: they closed it themselves.
      return "";
    case "auth/operation-not-allowed":
      return "Google sign-in is not switched on in Firebase. In the console: Authentication → Sign-in method → add Google.";
    case "auth/unauthorized-domain":
      return "This address is not on the Firebase authorised-domains list. An administrator has to add it in the Firebase console.";
    default:
      return err instanceof Error ? err.message : "Could not sign in with Google.";
  }
}

/* ---------------------------------------------------------------------------
 * Email and password, held by Firebase
 *
 * The password lives in Firebase, not in our database. That is the whole point
 * of routing it here: one place decides whether a person is who they say they
 * are, and our server only ever asks "is this proven address on the list?".
 *
 * `email_verified` is not optional on this route, and the reason is worth
 * stating plainly. Firebase lets anybody register ANY address — proving you
 * own it is a separate step. So a stranger could sign up as a colleague's
 * work address, and the allowlist would happily wave them through, because
 * the address really is on it. The verification email is what closes that.
 * ------------------------------------------------------------------------ */

/** Where Firebase sends people back to after they confirm the address. */
function returnUrl(): string {
  return `${window.location.origin}${window.location.pathname}#/signin`;
}

/**
 * Create the Firebase account and send the confirmation email.
 *
 * Throws `auth/email-already-in-use` when the account exists — the caller
 * treats that as "you already signed up", not as a failure.
 */
export async function signUpWithPassword(address: string, password: string): Promise<void> {
  const sdk = await loadSdk();
  const { initializeApp, getApps } = sdk.app;
  const { getAuth, createUserWithEmailAndPassword, sendEmailVerification, signOut } = sdk.auth;

  const app = getApps().length ? getApps()[0] : initializeApp(config);
  const auth = getAuth(app);
  auth.useDeviceLanguage();

  const credential = await createUserWithEmailAndPassword(auth, address, password);
  await sendEmailVerification(credential.user, { url: returnUrl() });
  // They are not signed in until they confirm, so do not leave a half-session
  // sitting in the browser looking like success.
  await signOut(auth).catch(() => undefined);
}

/** Ask Firebase to send the confirmation email again. */
export async function resendVerification(address: string, password: string): Promise<void> {
  const sdk = await loadSdk();
  const { initializeApp, getApps } = sdk.app;
  const { getAuth, signInWithEmailAndPassword, sendEmailVerification, signOut } = sdk.auth;

  const app = getApps().length ? getApps()[0] : initializeApp(config);
  const auth = getAuth(app);
  const credential = await signInWithEmailAndPassword(auth, address, password);
  await sendEmailVerification(credential.user, { url: returnUrl() });
  await signOut(auth).catch(() => undefined);
}

/** Thrown when the password is right but the address was never confirmed. */
export class EmailNotVerified extends Error {
  readonly code = "auth/email-not-verified";
}

/** Sign in, and return the Firebase ID token for our server. */
export async function signInWithPassword(address: string, password: string): Promise<string> {
  const sdk = await loadSdk();
  const { initializeApp, getApps } = sdk.app;
  const { getAuth, signInWithEmailAndPassword, sendEmailVerification, signOut } = sdk.auth;

  const app = getApps().length ? getApps()[0] : initializeApp(config);
  const auth = getAuth(app);
  auth.useDeviceLanguage();

  const credential = await signInWithEmailAndPassword(auth, address, password);
  if (!credential.user.emailVerified) {
    // Send another one on the way out: somebody who reaches this point has
    // lost or never received the first, and telling them to look for an email
    // that is not there is the least useful thing this could do.
    await sendEmailVerification(credential.user, { url: returnUrl() }).catch(() => undefined);
    await signOut(auth).catch(() => undefined);
    throw new EmailNotVerified(
      "Confirm your email address first. We have sent the link again — check your inbox, and the spam folder.",
    );
  }

  const token = await credential.user.getIdToken();
  await signOut(auth).catch(() => undefined);
  return token;
}

/** Firebase emails the reset link itself — free, to any address. */
export async function sendPasswordReset(address: string): Promise<void> {
  const sdk = await loadSdk();
  const { initializeApp, getApps } = sdk.app;
  const { getAuth, sendPasswordResetEmail } = sdk.auth;

  const app = getApps().length ? getApps()[0] : initializeApp(config);
  const auth = getAuth(app);
  auth.useDeviceLanguage();
  await sendPasswordResetEmail(auth, address, { url: returnUrl() });
}

/** Turn a Firebase password error into something worth showing a person. */
export function passwordErrorMessage(err: unknown): string {
  const code = (err as { code?: string })?.code ?? "";
  switch (code) {
    case "sdk/unavailable":
      return "Could not reach Google to sign in. Check the connection and try again.";
    case "auth/email-not-verified":
      return err instanceof Error ? err.message : "Confirm your email address first.";
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      // One message for both, deliberately: separate ones tell a stranger
      // which addresses have accounts here.
      return "That email address and password do not match.";
    case "auth/email-already-in-use":
      return "That address already has a password. Use Sign in, or Forgot password.";
    case "auth/weak-password":
      return "That password is too weak. Use at least 10 characters.";
    case "auth/invalid-email":
      return "That does not look like an email address.";
    case "auth/too-many-requests":
      return "Too many attempts from this device. Wait a few minutes, then try again.";
    case "auth/operation-not-allowed":
      return "Email and password sign-in is not switched on in Firebase. In the console: Authentication → Sign-in method → Email/Password.";
    case "auth/unauthorized-domain":
      return "This address is not on the Firebase authorised-domains list. An administrator has to add it.";
    default:
      return err instanceof Error ? err.message : "Could not sign in.";
  }
}
