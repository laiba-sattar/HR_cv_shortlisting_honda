/**
 * Backend API client.
 *
 * If the backend is not running, `checkBackend()` returns null and the app
 * falls back to the built-in demo simulation — so the site is always usable,
 * and it always tells you which mode it is in rather than quietly faking it.
 */

/**
 * Where the API lives.
 *
 * Deployed, the site and the API are served from one address, so an empty base
 * means "same origin" — and the site can never be up while the API it depends
 * on is somewhere else. In development they are two processes on two ports, so
 * the dev build points at the local backend. VITE_API_URL overrides both.
 */
const BASE = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

export type RequirementField = {
  mentioned: boolean;
  quoted_text: string | null;
  min_value: number | null;
  max_value: number | null;
  level: string | null;
  field_of_study: string | null;
};

export type JDAnalysis = {
  job_title: string;
  summary: string | null;
  detected_skills: string[];
  preferred_skills: string[];
  requirements: Record<"qualification" | "experience" | "age", RequirementField>;
  missing_requirements: string[];
  jd_filename: string | null;
};

export type Health = {
  status: string;
  llm_provider: string;
  llm_model: string;
  embed_provider: string;
  embed_model: string;
  semantic_matching_real: boolean;
  warnings: string[];
};

export type ApiCandidate = {
  candidate_name: string;
  /**
   * Read out of the CV by the extractor, and carried all the way here.
   *
   * These were being dropped on this side: the server has sent them since the
   * scorer started keeping them, but the type did not name them, so the mapper
   * wrote an empty string and a reviewer had a ranked list of people with no
   * way to contact any of them without reopening the files.
   *
   * Null when the CV did not state one. Never used in scoring.
   */
  email?: string | null;
  phone?: string | null;
  final_score: number;
  scores: { qualification: number; experience: number; jd_skills: number };
  explanations: { qualification: string; experience: string; jd_skills: string };
  details: {
    qualification: Record<string, unknown>;
    experience: {
      relevant_years?: number;
      total_years?: number;
      roles?: Array<{
        job_title: string;
        employer: string | null;
        duration_years: number;
        employment_type: string;
        relevance: number;
        weighted_years: number;
      }>;
    };
    jd_skills: {
      skill_matches?: Array<{
        required_skill: string;
        matched_skill: string | null;
        similarity: number;
        credit: number;
        method: string;
        reasoning: string | null;
      }>;
    };
  };
  matched_skills: string[];
  missing_skills: string[];
  flags: string[];
  source_file: string | null;
};

export type RunStatus = {
  id: string;
  title: string;
  status: "processing" | "completed" | "failed";
  created_at: string;
  created_by: string;
  version: number;
  top_n: number;
  required_skills: string[];
  progress: { done: number; total: number; current: string | null };
  failures: Array<{ path: string; reason: string }>;
  versions: Record<string, string>;
  error: string | null;
  requirements?: Record<string, RequirementField>;
  results?: { ranking: ApiCandidate[] };
  total_candidates?: number;
};

export class ApiError extends Error {
  status: number;
  payload?: unknown;

  constructor(message: string, status: number, payload?: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let payload: unknown;
    let message = `Request failed (${res.status})`;
    try {
      payload = await res.json();
      const p = payload as { message?: string; detail?: string; error?: string };
      message = p.message || p.detail || p.error || message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, res.status, payload);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Signing in
// ---------------------------------------------------------------------------

export type SignedInUser = {
  email: string;
  name: string;
  role: "hr" | "admin";
};

export type SignInOptions = {
  email: boolean;
  phone: boolean;
  /** Firebase can prove an address — by emailed link or by Google. */
  firebase_email: boolean;
  open_access: boolean;
  warnings: string[];
};

export type ManagedUser = {
  email: string;
  phone: string | null;
  name: string;
  role: string;
  active: number;
  added_at: string;
  added_by: string | null;
};

/**
 * Every call carries the session cookie.
 *
 * The cookie is httpOnly, so this code cannot read it — which is the point:
 * a script injected into the page cannot steal a session it cannot see. The
 * browser attaches it, and `credentials: "include"` is what tells it to.
 */
const withSession: RequestInit = { credentials: "include" };

export async function signInOptions(): Promise<SignInOptions> {
  return handle<SignInOptions>(await fetch(`${BASE}/api/auth/options`, withSession));
}

export type SignInResult = {
  /** "signed_in" — done, go to the workspace.
   *  "code_sent" — a code was emailed; ask for it next. */
  status: "signed_in" | "code_sent";
  user?: SignedInUser;
  email?: string;
};

/**
 * The one sign-in call: an address and a password.
 *
 * The server decides what happens. Somebody who has signed in before is let
 * straight in; somebody who has not is emailed a code, and the password they
 * typed is held until that code comes back. Either way an address nobody
 * authorised is refused before any email is sent.
 */
export async function signIn(email: string, password: string): Promise<SignInResult> {
  return handle<SignInResult>(
    await fetch(`${BASE}/api/auth/signin`, {
      ...withSession,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
  );
}

/** Forgotten password: choose a new one, then confirm by emailed code. */
export async function resetPassword(email: string, password: string): Promise<SignInResult> {
  return handle<SignInResult>(
    await fetch(`${BASE}/api/auth/reset`, {
      ...withSession,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
  );
}

/**
 * Finish a phone sign-in.
 *
 * Firebase has already checked the SMS code by this point; the token only
 * proves the number. The server decides whether that number is allowed in.
 */
export async function signInWithPhone(idToken: string): Promise<SignedInUser> {
  return handle<SignedInUser>(
    await fetch(`${BASE}/api/auth/phone/verify`, {
      ...withSession,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    })
  );
}

/**
 * Finish a Firebase email sign-in — an emailed link, or Google.
 *
 * Firebase has already confirmed the mailbox by this point; the token only
 * proves the address. The server decides whether that address is allowed in,
 * against the same list every other route checks.
 */
export async function signInWithFirebaseEmail(idToken: string): Promise<SignedInUser> {
  return handle<SignedInUser>(
    await fetch(`${BASE}/api/auth/firebase/verify`, {
      ...withSession,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    })
  );
}

export async function requestSignInCode(email: string): Promise<{ expires_in_minutes: number }> {
  return handle(
    await fetch(`${BASE}/api/auth/email/request`, {
      ...withSession,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    })
  );
}

export async function verifySignInCode(email: string, code: string): Promise<SignedInUser> {
  return handle<SignedInUser>(
    await fetch(`${BASE}/api/auth/email/verify`, {
      ...withSession,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code }),
    })
  );
}

/** Who is signed in, or null. Never throws for "nobody". */
export async function whoAmI(): Promise<SignedInUser | null> {
  try {
    const res = await fetch(`${BASE}/api/auth/me`, withSession);
    if (res.status === 401) return null;
    return await handle<SignedInUser>(res);
  } catch {
    // Backend unreachable is not the same as signed out, but from the page's
    // point of view both mean "do not show the workspace yet".
    return null;
  }
}

export async function signOut(): Promise<void> {
  await fetch(`${BASE}/api/auth/logout`, { ...withSession, method: "POST" });
}

export async function listManagedUsers(): Promise<{ users: ManagedUser[] }> {
  return handle(await fetch(`${BASE}/api/auth/users`, withSession));
}

export async function addManagedUser(body: {
  email: string;
  name: string;
  role: string;
  phone?: string;
}): Promise<{ user: ManagedUser }> {
  return handle(
    await fetch(`${BASE}/api/auth/users`, {
      ...withSession,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
}

export async function setManagedUserActive(email: string, active: boolean) {
  return handle(
    await fetch(
      `${BASE}/api/auth/users/${encodeURIComponent(email)}/active?active=${active}`,
      { ...withSession, method: "POST" }
    )
  );
}

/**
 * Returns health info if the backend is reachable, otherwise null.
 *
 * Retries a few times before giving up: a freshly started backend may still
 * be downloading its embedding model, and reporting "not reachable" while it
 * is in fact starting up correctly is worse than waiting a moment.
 */
export async function checkBackend(
  timeoutMs = 8000,
  attempts = 3,
  gapMs = 2000
): Promise<Health | null> {
  for (let i = 0; i < attempts; i++) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), timeoutMs);
      const res = await fetch(`${BASE}/api/health`, { signal: ctrl.signal });
      clearTimeout(t);
      if (res.ok) return (await res.json()) as Health;
    } catch {
      /* not up yet — fall through to retry */
    }
    if (i < attempts - 1) await new Promise((r) => setTimeout(r, gapMs));
  }
  return null;
}

export async function analyzeJD(opts: {
  file?: File | null;
  text?: string;
  jobTitle?: string;
}): Promise<JDAnalysis> {
  const fd = new FormData();
  if (opts.file) fd.append("jd_file", opts.file);
  if (opts.text) fd.append("jd_text", opts.text);
  if (opts.jobTitle) fd.append("job_title", opts.jobTitle);
  return handle<JDAnalysis>(await fetch(`${BASE}/api/jd/analyze`, { ...withSession, method: "POST", body: fd }));
}

export type ManualOverrides = Record<
  string,
  { text?: string; min_value?: number | null; max_value?: number | null }
>;

export async function createRun(opts: {
  jobTitle: string;
  jdFile?: File | null;
  jdText?: string;
  cvFiles: File[];
  requiredSkills: string[];
  manualOverrides: ManualOverrides;
  topN: number;
}): Promise<{ run_id: string; total: number; rejected: Array<{ path: string; reason: string }> }> {
  const fd = new FormData();
  fd.append("job_title", opts.jobTitle);
  if (opts.jdFile) fd.append("jd_file", opts.jdFile);
  if (opts.jdText) fd.append("jd_text", opts.jdText);
  fd.append("required_skills", JSON.stringify(opts.requiredSkills));
  fd.append("manual_overrides", JSON.stringify(opts.manualOverrides));
  fd.append("top_n", String(opts.topN));
  opts.cvFiles.forEach((f) => fd.append("cvs", f));
  return handle(await fetch(`${BASE}/api/runs`, { ...withSession, method: "POST", body: fd }));
}

export async function getRun(runId: string, topN?: number): Promise<RunStatus> {
  const q = topN ? `?top_n=${topN}` : "";
  return handle<RunStatus>(await fetch(`${BASE}/api/runs/${runId}${q}`, withSession));
}

export async function listRuns(): Promise<{ runs: Array<Omit<RunStatus, "results">> }> {
  return handle(await fetch(`${BASE}/api/runs`, withSession));
}

export async function deleteRun(runId: string): Promise<void> {
  await handle(await fetch(`${BASE}/api/runs/${runId}`, { ...withSession, method: "DELETE" }));
}

export async function getAudit(limit = 200): Promise<{
  entries: Array<{ at: string; actor: string; action: string; run_id: string | null; detail: string | null }>;
  /** How many entries the log holds in total, not just on this page. */
  total?: number;
  limit?: number;
}> {
  return handle(await fetch(`${BASE}/api/audit?limit=${limit}`, withSession));
}

/** Poll a run until it finishes. Calls onProgress on each tick. */
export async function pollRun(
  runId: string,
  onProgress: (s: RunStatus) => void,
  intervalMs = 900,
  timeoutMs = 15 * 60 * 1000
): Promise<RunStatus> {
  const started = Date.now();
  for (;;) {
    const status = await getRun(runId);
    onProgress(status);
    if (status.status === "completed" || status.status === "failed") return status;
    if (Date.now() - started > timeoutMs) {
      throw new ApiError("Ranking timed out.", 504);
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
