/// <reference types="vite/client" />

/**
 * The Firebase web config, read from .env at build time.
 *
 * Declared so a typo in a variable name is a compile error rather than a
 * silently undefined value that only shows up as a broken sign-in.
 * None of these are secrets — see src/firebase.ts.
 */
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_FIREBASE_API_KEY?: string;
  readonly VITE_FIREBASE_AUTH_DOMAIN?: string;
  readonly VITE_FIREBASE_PROJECT_ID?: string;
  readonly VITE_FIREBASE_APP_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
