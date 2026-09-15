import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Copy,
  Download,
  FileText,
  Loader2,
  Pencil,
  RefreshCw,
  Search,
  Upload,
  X,
  XCircle,
} from "lucide-react";
import AppHeader from "../components/AppHeader";
import { scoreTone } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useAuth } from "../context/AuthContext";
import { analyzeJD, extractSkills, simulateFileOutcome } from "../utils/simulate";
import { generateCandidates } from "../data/generate";
import * as api from "../api";
import type { ApiCandidate, Health, JDAnalysis } from "../api";
import type { Candidate, FileItem, JDProfile, JobRun } from "../types";

type FieldKey = "age" | "experience" | "qualification";
const FIELD_LABELS: Record<FieldKey, string> = {
  age: "Age requirement",
  experience: "Experience requirement",
  qualification: "Required qualification",
};
const FIELD_ORDER: FieldKey[] = ["qualification", "experience", "age"];
const MAX_FILES = 100;
const VALID_EXT = [".pdf", ".doc", ".docx", ".txt"];

type Phase = "idle" | "processing" | "done";

// ---------------------------------------------------------------------------
// Small building blocks local to this page
// ---------------------------------------------------------------------------

/** A section heading, with a short red rule set before it. */
const PanelLabel: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="label flex items-center gap-2">
    <span aria-hidden className="h-3 w-[3px] rounded-full bg-honda-red" />
    {children}
  </p>
);

const FieldLabel: React.FC<{ children: React.ReactNode; hint?: string }> = ({ children, hint }) => (
  <div className="mb-2">
    <label className="text-sm font-semibold text-ink-900">{children}</label>
    {hint && <p className="mt-1 text-xs leading-snug text-ink-500">{hint}</p>}
  </div>
);

const inputClass = "field field-sm";

// ---------------------------------------------------------------------------
// Mapping the backend's shapes onto the ones the UI already renders, so the
// same components work in both live and demo mode.
// ---------------------------------------------------------------------------

function jdAnalysisToProfile(a: JDAnalysis, fileName: string): JDProfile {
  const f = (k: "qualification" | "experience" | "age") => ({
    found: a.requirements[k]?.mentioned ?? false,
    jdValue: a.requirements[k]?.quoted_text ?? undefined,
  });
  return {
    fileName: a.jd_filename || fileName || "pasted text",
    uploadedAt: new Date().toISOString(),
    detectedSkills: a.detected_skills || [],
    qualification: f("qualification"),
    experience: f("experience"),
    age: f("age"),
  };
}

function apiCandidateToCandidate(c: ApiCandidate, index: number): Candidate {
  const parts = c.candidate_name.trim().split(/\s+/);
  const initials = ((parts[0]?.[0] ?? "?") + (parts[1]?.[0] ?? "")).toUpperCase();
  const roles = c.details?.experience?.roles ?? [];
  const qualText = String(
    (c.details?.qualification as Record<string, unknown>)?.candidate_qualification ?? "—"
  );
  return {
    id: `api-${index}-${c.candidate_name}`,
    name: c.candidate_name,
    initials,
    email: c.email ?? "",
    phone: c.phone ?? "",
    cvFileName: c.source_file ? c.source_file.split(/[\\/]/).pop() || "" : "",
    qualifications: [
      { degree: qualText, field: "", institution: "", year: "" },
    ],
    experience: roles.map((r) => ({
      title: r.job_title,
      employer: r.employer || "",
      period: `${r.duration_years} yrs`,
      years: r.duration_years,
      description: `${r.employment_type.replace("_", " ")} — ${r.weighted_years.toFixed(1)} weighted years`,
      relevance: r.relevance,
    })),
    skills: c.matched_skills,
    matchedSkills: c.matched_skills,
    missingSkills: c.missing_skills,
    scores: {
      qualification: c.scores.qualification,
      experience: c.scores.experience,
      jdSkills: c.scores.jd_skills,
      final: c.final_score,
    },
    relevantYears: c.details?.experience?.relevant_years ?? 0,
    status: "Undecided",
    notes: "",
    flagged: (c.flags?.length ?? 0) > 0,
  };
}

/**
 * One headline number from the run.
 *
 * A KPI row, not a chart: four single values have no shape to plot, and a
 * four-bar bar chart of unrelated quantities would be a chart pretending the
 * numbers are comparable. They are not — one is a count, two are percentages,
 * one is a warning.
 */
const StatTile: React.FC<{
  label: string;
  value: string;
  note?: string;
  /** Only for the one tile that reports a problem. */
  alert?: boolean;
}> = ({ label, value, note, alert }) => (
  <div className="px-4 py-3.5">
    <p className="font-mono text-2xs font-medium uppercase tracking-[0.14em] text-bone/60">
      {label}
    </p>
    {/* Proportional figures, not tabular: these do not sit in a column, and
        tabular digits make a standalone number look loose at this size. */}
    <p className="mt-1.5 text-2xl font-semibold tracking-[-0.02em] text-bone">{value}</p>
    {note && (
      <p
        className={`mt-0.5 flex items-center gap-1 text-2xs leading-snug ${
          alert ? "font-semibold text-warning-track" : "text-bone/60"
        }`}
      >
        {/* The icon is not decoration. On a red ground an amber tint is a weak
            signal, and a status cue is never allowed to rest on colour alone. */}
        {alert && <AlertTriangle size={11} className="shrink-0" />}
        {note}
      </p>
    )}
  </div>
);

/** A compact meter: the label, the value in ink, and a same-ramp track. */
const MiniScore: React.FC<{ label: string; value: number }> = ({ label, value }) => {
  const tone = scoreTone(value);
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="font-mono text-2xs uppercase tracking-[0.12em] text-ink-500">{label}</span>
        <span className="tnum text-xs font-semibold text-ink-800">{value}%</span>
      </div>
      <div className={`h-1.5 overflow-hidden rounded-full ${tone.track}`}>
        <div
          className={`h-full rounded-full ${tone.bar} transition-all duration-500 ease-out`}
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
};

/**
 * One candidate, as a card.
 *
 * Off-white card, one red rule along the top, red actions and a red strip at
 * the foot — the same construction the sign-in card uses, so the two screens
 * are visibly one product.
 *
 * The coloured meters are back. They were dropped when this card was black,
 * because on a near-black ground the three score colours cannot be made
 * colourblind-safe: squeezed into the lightness band a dark surface needs, the
 * amber and the red collapse to a delta of 3.4 under deuteranopia. On a light
 * ground the validated palette applies again, and the bars can carry the
 * comparison the way they do everywhere else.
 */
const CandidateCard: React.FC<{
  candidate: Candidate;
  rank: number;
  role: string;
  open: boolean;
  copied: boolean;
  onToggle: () => void;
  onCopyEmail: () => void;
}> = ({ candidate: c, rank, role, open, copied, onToggle, onCopyEmail }) => {
  const hasEmail = Boolean(c.email);
  return (
    <div className="relative overflow-hidden rounded-xl3 bg-cream-50 shadow-[0_0_0_1px_rgba(14,16,19,0.07),0_1px_2px_rgba(14,16,19,0.04),0_10px_28px_-14px_rgba(14,16,19,0.18)]">
      {/* One rule, the same gradient as the sign-in card's. */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[3px]"
        style={{
          background:
            "linear-gradient(90deg, #CC0000 0%, #8C1A1E 42%, rgba(140,26,30,0) 100%)",
        }}
      />

      <div className="px-5 pb-4 pt-5">
        <div className="flex items-center justify-between gap-3">
          <p className="flex min-w-0 items-center gap-2 text-xs text-ink-500">
            <span className="tnum shrink-0 rounded bg-honda-red px-1.5 py-0.5 text-2xs font-bold text-white">
              {rank}
            </span>
            {/* The CV's file name, not the role. The role is the same on every
                card in a run, so printing it fourteen times said nothing —
                while the file name, which a reviewer needs to open the right
                document, had no place on the card at all. */}
            <span className="truncate font-mono">{c.cvFileName || role || "Candidate"}</span>
          </p>
          <p className="flex shrink-0 items-baseline gap-0.5">
            <span className="tnum text-lg font-semibold text-ink-900">{c.scores.final}</span>
            <span className="text-2xs font-medium text-ink-400">%</span>
          </p>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-ink-100 text-xs font-bold tracking-wide text-ink-600">
            {c.initials}
          </span>
          <div className="min-w-0">
            <p className="truncate text-md font-semibold text-ink-900">{c.name}</p>
            {/* The address, or the plain fact that the CV did not give one.
                A copy button with nothing behind it is worse than no button. */}
            <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs">
              <span
                aria-hidden
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  hasEmail ? "bg-honda-red" : "bg-ink-300"
                }`}
              />
              <span className={`truncate ${hasEmail ? "text-ink-600" : "text-ink-400"}`}>
                {hasEmail ? c.email : "No email in the CV"}
              </span>
            </p>
          </div>
        </div>

        <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-cream-200 pt-3.5">
          <MiniScore label="Qual" value={c.scores.qualification} />
          <MiniScore label="Exp" value={c.scores.experience} />
          <MiniScore label="Skills" value={c.scores.jdSkills} />
        </dl>

        <div className="mt-4 grid grid-cols-2 gap-2.5">
          <button
            onClick={onToggle}
            aria-expanded={open}
            className="focus-ring inline-flex items-center justify-center gap-1.5 rounded-lg bg-honda-red py-2.5 text-sm font-semibold text-white shadow-[0_1px_2px_rgba(140,26,30,0.28),0_6px_14px_-8px_rgba(140,26,30,0.5)] transition-colors hover:bg-honda-red-dark active:bg-honda-red-darker"
          >
            <ChevronDown
              size={14}
              className={`transition-transform ${open ? "rotate-180" : ""}`}
            />
            {open ? "Hide" : "Show"}
          </button>
          <button
            onClick={onCopyEmail}
            disabled={!hasEmail}
            title={hasEmail ? c.email : "This CV did not give an email address"}
            className="focus-ring inline-flex items-center justify-center gap-1.5 rounded-lg bg-honda-red py-2.5 text-sm font-semibold text-white shadow-[0_1px_2px_rgba(140,26,30,0.28),0_6px_14px_-8px_rgba(140,26,30,0.5)] transition-colors hover:bg-honda-red-dark active:bg-honda-red-darker disabled:bg-cream-200 disabled:text-ink-400 disabled:shadow-none"
          >
            {copied ? <CheckCircle2 size={14} /> : <Copy size={14} />}
            {copied ? "Copied" : "Copy email"}
          </button>
        </div>
      </div>

      {/* The strip along the foot, carrying a fact rather than a mood: how much
          of what the advert asked for this person actually evidenced. */}
      <div className="flex items-center justify-center gap-2 bg-honda-red px-4 py-2.5 text-center">
        {c.flagged ? (
          <>
            <AlertTriangle size={13} className="shrink-0 text-white" />
            <span className="text-xs font-semibold text-white">
              Low-confidence read. Open the CV before deciding
            </span>
          </>
        ) : (
          <>
            <CheckCircle2 size={13} className="shrink-0 text-white" />
            <span className="text-xs font-semibold text-white">
              Matched {c.matchedSkills.length} of{" "}
              {c.matchedSkills.length + c.missingSkills.length} required skills
            </span>
          </>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------

const Workspace: React.FC = () => {
  const { jobs, addJob, updateJob } = useApp();
  // The person actually signed in, not a hard-coded name: a saved run has to
  // record who ran it, or the audit trail says nothing.
  const { user } = useAuth();
  const userName = user?.name ?? user?.email ?? "Unknown";
  const [searchParams, setSearchParams] = useSearchParams();

  // --- Set-up state -------------------------------------------------------
  const [selectedRoleId, setSelectedRoleId] = useState<string>("");
  const [jobTitle, setJobTitle] = useState("");
  const [jdText, setJdText] = useState("");
  const [jdFile, setJdFile] = useState<{ name: string; sizeKb: number } | null>(null);
  const [analysis, setAnalysis] = useState<JDProfile | null>(null);
  const [manual, setManual] = useState<Record<FieldKey, string>>({
    age: "",
    experience: "",
    qualification: "",
  });
  const [editing, setEditing] = useState<Record<FieldKey, boolean>>({
    age: false,
    experience: false,
    qualification: false,
  });
  const [skills, setSkills] = useState<string[]>([]);
  const [skillInput, setSkillInput] = useState("");
  const [cvFiles, setCvFiles] = useState<FileItem[]>([]);

  // --- Run state ----------------------------------------------------------
  const [errors, setErrors] = useState<string[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [topN, setTopN] = useState<5 | 10 | 20 | 30>(10);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  /** Which card last had its address copied, so the button can say so. */
  const [copiedId, setCopiedId] = useState<string | null>(null);

  /**
   * Put a candidate's address on the clipboard.
   *
   * `navigator.clipboard` needs a secure context, so it is absent over plain
   * http on anything but localhost — the deployed site is https, but somebody
   * opening the built files off a LAN address would otherwise get a button
   * that silently did nothing. The textarea path is the fallback for exactly
   * that case, and a real failure says so rather than pretending it worked.
   */
  const copyEmail = async (c: Candidate) => {
    if (!c.email) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(c.email);
      } else {
        const box = document.createElement("textarea");
        box.value = c.email;
        box.setAttribute("readonly", "");
        box.style.position = "fixed";
        box.style.opacity = "0";
        document.body.appendChild(box);
        box.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(box);
        if (!ok) throw new Error("The browser refused the copy.");
      }
      setCopiedId(c.id);
      window.setTimeout(
        () => setCopiedId((id) => (id === c.id ? null : id)),
        1800
      );
    } catch {
      setErrors([
        `Could not copy the address. It is ${c.email} — select it from the card and copy it by hand.`,
      ]);
    }
  };
  const [minScore, setMinScore] = useState(0);
  const [savedNote, setSavedNote] = useState("");
  const [dragTarget, setDragTarget] = useState<"jd" | "cv" | null>(null);

  // --- Backend connection -------------------------------------------------
  const [backend, setBackend] = useState<Health | null>(null);
  const [backendChecked, setBackendChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [apiCandidates, setApiCandidates] = useState<ApiCandidate[]>([]);

  const jdInputRef = useRef<HTMLInputElement>(null);
  const cvInputRef = useRef<HTMLInputElement>(null);
  const requirementsRef = useRef<HTMLDivElement>(null);

  // Real File objects, kept out of React state because they can't be
  // serialised to localStorage alongside the rest of the run.
  const jdBlobRef = useRef<File | null>(null);
  const cvBlobsRef = useRef<Map<string, File>>(new Map());

  const connectBackend = React.useCallback(() => {
    setBackendChecked(false);
    api.checkBackend().then((h) => {
      setBackend(h);
      setBackendChecked(true);
    });
  }, []);

  useEffect(() => {
    connectBackend();
  }, [connectBackend]);

  // Arriving from the History page. Two different links land here:
  //
  //   /?role=job-1001   a locally saved role, restored from local state
  //   /?run=run-2041    a past ranking, fetched back from the server
  //
  // The second was linked from History but never handled here, so every
  // "open a past ranking" click landed on an empty workspace and looked like
  // the run had been lost. The rows are the only way back into a finished
  // ranking, so this was the whole History page doing nothing.
  useEffect(() => {
    const roleParam = searchParams.get("role");
    if (roleParam) {
      loadRole(roleParam);
      setSearchParams({}, { replace: true });
      return;
    }

    const runParam = searchParams.get("run");
    if (runParam) {
      void loadRun(runParam);
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Re-open a finished ranking from the server.
   *
   * Read-only by intent: it restores the requirements that applied and the
   * scores that were produced, but not the CV files, which the server does
   * not keep. Ranking again from here would therefore silently rank nothing,
   * so the uploader is left empty and the person has to add files themselves.
   */
  async function loadRun(id: string) {
    setPhase("processing");
    setErrors([]);
    try {
      const run = await api.getRun(id);
      const ranking = run.results?.ranking ?? [];

      setSelectedRoleId("");
      setJobTitle(run.title);
      setSkills(run.required_skills ?? []);
      setTopN((run.top_n as JobRun["topN"]) ?? 10);

      if (run.requirements) {
        const field = (k: "qualification" | "experience" | "age") => ({
          found: run.requirements?.[k]?.mentioned ?? false,
          jdValue: run.requirements?.[k]?.quoted_text ?? undefined,
        });
        setAnalysis({
          fileName: "",
          uploadedAt: run.created_at,
          detectedSkills: run.required_skills ?? [],
          qualification: field("qualification"),
          experience: field("experience"),
          age: field("age"),
        });
      }

      setJdFile(null);
      setCvFiles([]);
      setCandidates(ranking.map(apiCandidateToCandidate));
      setPhase(ranking.length ? "done" : "idle");
      setExpandedId(null);
    } catch (e) {
      setPhase("idle");
      setErrors([
        e instanceof Error
          ? `That ranking could not be opened. ${e.message}`
          : "That ranking could not be opened.",
      ]);
    }
  }

  function loadRole(id: string) {
    const job = jobs.find((j) => j.id === id);
    if (!job) return;
    setSelectedRoleId(id);
    setJobTitle(job.title);
    setSkills(job.requiredSkills);
    setAnalysis(job.jd);
    setManual({
      age: job.jd.age.manualValue ?? "",
      experience: job.jd.experience.manualValue ?? "",
      qualification: job.jd.qualification.manualValue ?? "",
    });
    setJdFile(job.jd.fileName ? { name: job.jd.fileName, sizeKb: 0 } : null);
    setCvFiles([]);
    setCandidates(job.candidates);
    setPhase(job.candidates.length ? "done" : "idle");
    setTopN(job.topN);
    setErrors([]);
    setExpandedId(null);
  }

  // --- JD handling --------------------------------------------------------
  const handleJdFiles = (files: File[]) => {
    const f = files[0];
    if (!f) return;
    jdBlobRef.current = f;
    setJdFile({ name: f.name, sizeKb: Math.max(1, Math.round(f.size / 1024)) });
    // Plain-text JDs can genuinely be read in the browser; PDFs/DOCX need the backend parser.
    if (/\.txt$/i.test(f.name)) {
      f.text().then((t) => setJdText(t));
    }
    setAnalysis(null);
  };

  /**
   * Runs the JD presence-check. Returns the profile *and* the resolved skill list,
   * because React state set here isn't readable until the next render — callers in
   * the same tick (e.g. handleRank) need the values directly.
   */
  const readRequirements = (): { profile: JDProfile; skills: string[] } | null => {
    if (!jdText.trim() && !jdFile) return null;
    const result = analyzeJD(jobTitle, jdText, jdFile?.name ?? "");
    setAnalysis(result);

    // Pre-fill the skills list from the advert, but never overwrite what the user typed.
    let resolvedSkills = skills;
    if (skills.length === 0) {
      const found = result.detectedSkills.length ? result.detectedSkills : extractSkills(jdText);
      if (found.length) {
        setSkills(found);
        resolvedSkills = found;
      }
    }
    return { profile: result, skills: resolvedSkills };
  };

  const addSkill = () => {
    const v = skillInput.trim();
    if (v && !skills.some((s) => s.toLowerCase() === v.toLowerCase())) {
      setSkills((s) => [...s, v]);
    }
    setSkillInput("");
  };

  const handleCvFiles = (files: File[]) => {
    const room = MAX_FILES - cvFiles.length;
    const accepted = files.slice(0, Math.max(0, room));
    const mapped: FileItem[] = accepted.map((f, i) => {
      const ext = "." + (f.name.split(".").pop()?.toLowerCase() ?? "");
      const valid = VALID_EXT.includes(ext);
      const id = `${Date.now()}-${i}-${f.name}`;
      if (valid) cvBlobsRef.current.set(id, f);
      return {
        id,
        name: f.name,
        sizeKb: Math.max(1, Math.round(f.size / 1024)),
        status: valid ? "queued" : "failed",
        error: valid ? undefined : `Unsupported file type (${ext || "unknown"})`,
      };
    });
    setCvFiles((prev) => [...prev, ...mapped]);
  };

  // --- Live backend paths -------------------------------------------------

  const readRequirementsLive = async (): Promise<JDProfile | null> => {
    if (!jdText.trim() && !jdBlobRef.current) return null;
    setBusy(true);
    try {
      const a = await api.analyzeJD({
        file: jdBlobRef.current,
        text: jdText || undefined,
        jobTitle: jobTitle || undefined,
      });
      const profile = jdAnalysisToProfile(a, jdFile?.name ?? "");
      setAnalysis(profile);
      if (!jobTitle && a.job_title) setJobTitle(a.job_title);
      if (skills.length === 0 && a.detected_skills.length) setSkills(a.detected_skills);
      setErrors([]);
      return profile;
    } catch (e) {
      setErrors([e instanceof Error ? e.message : "Could not analyse the job description."]);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const handleRankLive = async () => {
    const problems: string[] = [];
    if (!jobTitle.trim()) problems.push("Job title is required.");
    if (!jdText.trim() && !jdBlobRef.current) {
      problems.push("A job description is required — upload a file or paste the advert text.");
    }
    const cvBlobs = cvFiles
      .filter((f) => f.status !== "failed")
      .map((f) => cvBlobsRef.current.get(f.id))
      .filter((f): f is File => !!f);
    if (cvBlobs.length === 0) problems.push("Upload at least one valid CV.");

    // Run the JD check BEFORE deciding anything else. Without this the
    // requirement fields never render, and the error told the user to fill in
    // a field under a section that wasn't on screen — so they typed the value
    // into the skills box instead, which was entirely our fault.
    let jd = analysis;
    if (!jd && (jdText.trim() || jdBlobRef.current)) {
      jd = await readRequirementsLive();
    }

    let missingRequirement = false;
    if (jd) {
      for (const key of FIELD_ORDER) {
        if (!jd[key].found && !manual_(key)) {
          missingRequirement = true;
          problems.push(
            `${FIELD_LABELS[key]} was not found in the job description — enter it in the box under “Requirements found in the advert”.`
          );
        }
      }
    }

    if (problems.length) {
      setErrors(problems);
      setPhase("idle");
      // Scroll to the fields that need filling in — they are now rendered.
      if (missingRequirement) {
        requirementsRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return;
    }

    const manual: api.ManualOverrides = {};
    for (const key of FIELD_ORDER) {
      if (manual_(key)) manual[key] = { text: manual_(key) };
    }

    setErrors([]);
    setExpandedId(null);
    setPhase("processing");
    setCandidates([]);
    setApiCandidates([]);
    setCvFiles((prev) => prev.map((f) => (f.status === "failed" ? f : { ...f, status: "queued" })));

    try {
      const { run_id } = await api.createRun({
        jobTitle,
        jdFile: jdBlobRef.current,
        jdText: jdText || undefined,
        cvFiles: cvBlobs,
        requiredSkills: skills,
        manualOverrides: manual,
        topN: topN,
      });

      const final = await api.pollRun(run_id, (s) => {
        const done = s.progress.done;
        setCvFiles((prev) =>
          prev.map((f, i) =>
            f.status === "failed" ? f : { ...f, status: i < done ? "done" : "queued" }
          )
        );
      });

      if (final.status === "failed") {
        setErrors([final.error || "Ranking failed on the server."]);
        setPhase("idle");
        return;
      }

      const ranking = final.results?.ranking ?? [];
      setApiCandidates(ranking);
      setCandidates(ranking.map(apiCandidateToCandidate));
      setCvFiles((prev) =>
        prev.map((f) => {
          const failed = final.failures.find((x) => x.path === f.name);
          return failed
            ? { ...f, status: "failed" as const, error: failed.reason }
            : { ...f, status: "done" as const };
        })
      );
      setPhase("done");
    } catch (e) {
      const msg = e instanceof api.ApiError && e.payload
        ? (() => {
            const p = e.payload as { error?: string; missing?: string[]; message?: string };
            if (p.error === "missing_requirements" && p.missing) {
              return p.missing.map(
                (k) => `${FIELD_LABELS[k as FieldKey]} was not found in the job description — enter it manually under “Requirements found in the advert”.`
              );
            }
            return [p.message || e.message];
          })()
        : [e instanceof Error ? e.message : "Ranking failed."];
      setErrors(Array.isArray(msg) ? msg : [msg]);
      setPhase("idle");
    }
  };

  const manual_ = (k: FieldKey) => manual[k].trim();

  // --- The one button -----------------------------------------------------
  const handleRank = () => {
    if (backend) {
      void handleRankLive();
      return;
    }
    const problems: string[] = [];

    if (!jobTitle.trim()) problems.push("Job title is required.");
    if (!jdText.trim() && !jdFile) {
      problems.push("A job description is required — upload a file or paste the advert text.");
    }

    // Step 1: always run the JD requirement check first.
    let jd = analysis;
    let effectiveSkills = skills;
    if (!jd && (jdText.trim() || jdFile)) {
      const read = readRequirements();
      if (read) {
        jd = read.profile;
        effectiveSkills = read.skills;
      }
    }

    let missingRequirement = false;
    if (jd) {
      for (const key of FIELD_ORDER) {
        if (!jd[key].found && !manual[key].trim()) {
          missingRequirement = true;
          problems.push(
            `${FIELD_LABELS[key]} was not found in the job description — enter it manually under “Requirements found in the advert”.`
          );
        }
      }
    }

    if (effectiveSkills.length === 0) problems.push("Add at least one required skill.");
    const validCvs = cvFiles.filter((f) => f.status !== "failed");
    if (validCvs.length === 0) problems.push("Upload at least one valid CV.");

    if (problems.length > 0) {
      setErrors(problems);
      setPhase("idle");
      // Jump to the fields that need filling in; otherwise the error panel on the
      // right is already in view (it's sticky).
      if (missingRequirement) {
        requirementsRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return;
    }

    // Step 2: everything checks out — process and score.
    setErrors([]);
    setExpandedId(null);
    setPhase("processing");
    setCandidates([]);
    runProcessing(validCvs, jd!, effectiveSkills);
  };

  const runProcessing = (queue: FileItem[], jd: JDProfile, runSkills: string[]) => {
    setCvFiles((prev) => prev.map((f) => (f.status === "failed" ? f : { ...f, status: "queued" })));
    let i = 0;

    const step = () => {
      if (i >= queue.length) {
        finish(jd);
        return;
      }
      const target = queue[i];
      setCvFiles((prev) =>
        prev.map((f) => (f.id === target.id ? { ...f, status: "processing" } : f))
      );
      setTimeout(() => {
        const outcome = simulateFileOutcome();
        setCvFiles((prev) =>
          prev.map((f) =>
            f.id === target.id
              ? outcome.failed
                ? { ...f, status: "failed", error: outcome.reason }
                : { ...f, status: "done" }
              : f
          )
        );
        i += 1;
        setTimeout(step, 60 + Math.random() * 90);
      }, 120 + Math.random() * 180);
    };

    const finish = (jdProfile: JDProfile) => {
      setCvFiles((current) => {
        const successCount = current.filter((f) => f.status === "done").length;
        const generated = generateCandidates(successCount, runSkills);
        setCandidates(generated);
        setPhase("done");
        persistRun(jdProfile, current, generated, runSkills);
        return current;
      });
    };

    step();
  };

  const persistRun = (
    jd: JDProfile,
    files: FileItem[],
    results: Candidate[],
    runSkills: string[] = skills
  ) => {
    const jdWithManual: JDProfile = {
      ...jd,
      age: { ...jd.age, manualValue: manual.age || undefined },
      experience: { ...jd.experience, manualValue: manual.experience || undefined },
      qualification: { ...jd.qualification, manualValue: manual.qualification || undefined },
    };
    if (selectedRoleId && jobs.some((j) => j.id === selectedRoleId)) {
      const existing = jobs.find((j) => j.id === selectedRoleId)!;
      updateJob(selectedRoleId, {
        title: jobTitle,
        requiredSkills: runSkills,
        jd: jdWithManual,
        files,
        candidates: results,
        status: "Completed",
        topN,
        version: existing.version + 1,
      });
    } else {
      const id = `job-${Date.now()}`;
      const run: JobRun = {
        id,
        title: jobTitle,
        status: "Completed",
        createdAt: new Date().toISOString(),
        createdBy: userName,
        requiredSkills: runSkills,
        jd: jdWithManual,
        files,
        candidates: results,
        topN,
        version: 1,
      };
      addJob(run);
      setSelectedRoleId(id);
    }
  };

  const handleSaveRole = () => {
    if (!jobTitle.trim()) {
      setErrors(["Enter a job title before saving this role."]);
      return;
    }
    const read = analysis ? null : readRequirements();
    const jdProfile: JDProfile =
      analysis ??
      read?.profile ??
      ({
        fileName: jdFile?.name ?? "not provided",
        uploadedAt: new Date().toISOString(),
        detectedSkills: [],
        age: { found: false },
        experience: { found: false },
        qualification: { found: false },
      } as JDProfile);

    persistRun(jdProfile, cvFiles, candidates, read?.skills ?? skills);
    setSavedNote("Role saved");
    setTimeout(() => setSavedNote(""), 2200);
  };

  const resetAll = () => {
    setSelectedRoleId("");
    setJobTitle("");
    setJdText("");
    setJdFile(null);
    setAnalysis(null);
    setManual({ age: "", experience: "", qualification: "" });
    setSkills([]);
    setCvFiles([]);
    setCandidates([]);
    setPhase("idle");
    setErrors([]);
    setExpandedId(null);
  };

  const exportCsv = () => {
    const rows = [
      ["Rank", "Candidate", "Final Score", "Qualification", "Experience", "JD & Skills", "Status"],
      ...visible.map((c, i) => [
        String(i + 1),
        c.name,
        `${c.scores.final}%`,
        `${c.scores.qualification}%`,
        `${c.scores.experience}%`,
        `${c.scores.jdSkills}%`,
        c.status,
      ]),
    ];
    const csv = rows.map((r) => r.map((v) => `"${v}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(jobTitle || "shortlist").replace(/\s+/g, "_")}_shortlist.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const processedCount = cvFiles.filter((f) => f.status === "done" || f.status === "failed").length;
  const failedFiles = cvFiles.filter((f) => f.status === "failed");
  const failedCount = failedFiles.length;
  // A rate-limited CV is not a broken CV. Saying "could not be read" sends the
  // reviewer off to check the PDF, when the file was fine and the AI service
  // simply asked us to slow down — and the fix is to run it again, not to
  // re-export the document.
  const rateLimitedCount = failedFiles.filter((f) =>
    /rate.?limit|429|too many requests|tokens per minute/i.test(f.error || "")
  ).length;
  const unreadableCount = failedCount - rateLimitedCount;
  const progressPct = cvFiles.length ? Math.round((processedCount / cvFiles.length) * 100) : 0;

  const visible = candidates
    .filter((c) => c.scores.final >= minScore)
    .slice(0, topN);

  // Run-level figures for the summary tiles. Computed over ALL candidates, not
  // the filtered view: these describe what the ranking found, and a median that
  // moved every time somebody dragged the minimum-score slider would describe
  // the slider instead.
  const allScores = candidates.map((c) => c.scores.final).sort((a, b) => a - b);
  const topScore = allScores.length ? Math.round(allScores[allScores.length - 1]) : 0;
  const topScoreBand = allScores.length ? `${scoreTone(topScore).label.toLowerCase()} match` : "";
  const medianScore = allScores.length
    ? Math.round(
        allScores.length % 2
          ? allScores[(allScores.length - 1) / 2]
          : (allScores[allScores.length / 2 - 1] + allScores[allScores.length / 2]) / 2
      )
    : 0;
  const flaggedCount = candidates.filter((c) => c.flagged).length;

  const requirementValue = (key: FieldKey) =>
    manual[key].trim() || analysis?.[key].jdValue || "Not specified";

  return (
    // `page-ground`: the faint red wash under the header, defined once in
    // index.css so this page and the three that use Layout cannot drift apart.
    <div className="page-ground min-h-screen">
      <AppHeader />

      <main className="mx-auto grid w-full max-w-[1500px] grid-cols-1 gap-6 px-5 py-6 lg:grid-cols-[minmax(360px,420px)_1fr] lg:px-8">
        {/* ================= SET UP ================= */}
        <section className="rounded-lg border border-cream-300 bg-white p-5">
          {/* Which mode the app is actually in — never leave this ambiguous */}
          {!backendChecked && (
            <div className="mb-4 flex items-center gap-2 rounded-md bg-cream-100 px-3 py-2 text-xs text-ink-500">
              <Loader2 size={12} className="animate-spin" />
              Connecting to the backend…
            </div>
          )}
          {backendChecked && (
            <div
              className={`mb-4 flex items-start gap-2 rounded-md px-3 py-2 text-xs leading-snug ${
                backend
                  ? backend.semantic_matching_real
                    ? "bg-success-light text-success"
                    : "bg-warning-light text-warning"
                  : "bg-cream-100 text-ink-500"
              }`}
            >
              <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
              <span>
                {backend ? (
                  <>
                    <span className="font-bold">Live backend</span>{" "}
                    <span className="opacity-80">
                      {backend.llm_provider} / {backend.embed_provider}
                    </span>
                    {backend.warnings.length > 0 && (
                      <span className="mt-0.5 block opacity-90">{backend.warnings[0]}</span>
                    )}
                  </>
                ) : (
                  <>
                    <span className="font-bold">Demo mode.</span> Backend not reachable, using
                    simulated data. Start it with <code>uvicorn api.main:app --port 8000</code>,
                    then{" "}
                    <button
                      onClick={connectBackend}
                      className="focus-ring font-bold text-honda-red underline underline-offset-2"
                    >
                      retry
                    </button>
                    .
                  </>
                )}
              </span>
            </div>
          )}

          <div className="mb-4 flex items-center justify-between">
            <PanelLabel>Set up</PanelLabel>
            {(jobTitle || cvFiles.length > 0 || candidates.length > 0) && (
              <button
                onClick={resetAll}
                className="focus-ring rounded px-1.5 py-0.5 text-xs font-semibold text-ink-400 hover:text-honda-red"
              >
                Clear
              </button>
            )}
          </div>

          {/* Saved roles */}
          <FieldLabel>Saved roles</FieldLabel>
          <div className="flex gap-2">
            <select
              value={selectedRoleId}
              onChange={(e) => (e.target.value ? loadRole(e.target.value) : resetAll())}
              className={inputClass}
            >
              <option value="">New role</option>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.title}
                </option>
              ))}
            </select>
            <button
              onClick={handleSaveRole}
              className="focus-ring shrink-0 rounded-md border border-honda-red/25 bg-honda-red-tint text-honda-red transition-colors hover:border-honda-red/45 hover:bg-honda-red-light px-3.5 py-2 text-sm font-semibold"
            >
              Save
            </button>
          </div>
          {savedNote && (
            <p className="mt-1.5 text-xs font-semibold text-success">{savedNote}</p>
          )}

          <hr className="my-5 border-cream-200" />

          {/* Job title */}
          <FieldLabel>Job title</FieldLabel>
          <input
            value={jobTitle}
            onChange={(e) => setJobTitle(e.target.value)}
            placeholder="e.g. Mechanical Design Engineer"
            className={inputClass}
          />

          {/* Job description */}
          <div className="mt-5">
            <FieldLabel hint="Upload the JD file, or paste the advert. Skills, experience and education are read from it.">
              Job description
            </FieldLabel>

            {jdFile ? (
              <div className="mb-2 flex items-center justify-between rounded-md border border-cream-300 bg-cream-50 px-3 py-2">
                <span className="flex min-w-0 items-center gap-2">
                  <FileText size={15} className="shrink-0 text-honda-red" />
                  <span className="truncate text-xs font-semibold text-ink-800">
                    {jdFile.name}
                  </span>
                </span>
                <button
                  onClick={() => {
                    setJdFile(null);
                    setAnalysis(null);
                  }}
                  className="focus-ring rounded p-1 text-ink-400 hover:text-danger"
                >
                  <X size={14} />
                </button>
              </div>
            ) : (
              <button
                onClick={() => jdInputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragTarget("jd");
                }}
                onDragLeave={() => setDragTarget(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragTarget(null);
                  handleJdFiles(Array.from(e.dataTransfer.files));
                }}
                className={`focus-ring mb-2 flex w-full items-center justify-center gap-2 rounded-md border border-dashed px-3 py-2.5 text-xs font-semibold transition-colors ${
                  dragTarget === "jd"
                    ? "border-honda-red bg-honda-red-tint text-honda-red"
                    : "border-honda-red/30 bg-honda-red-tint text-honda-red hover:border-honda-red/60 hover:bg-honda-red-light"
                }`}
              >
                <Upload size={14} /> Drop the JD here, or click to choose
              </button>
            )}
            <input
              ref={jdInputRef}
              type="file"
              accept=".pdf,.doc,.docx,.txt"
              className="hidden"
              onChange={(e) => e.target.files && handleJdFiles(Array.from(e.target.files))}
            />

            <textarea
              value={jdText}
              onChange={(e) => {
                setJdText(e.target.value);
                setAnalysis(null);
              }}
              rows={6}
              placeholder="Paste the full job advert here, then choose Read requirements."
              className={`${inputClass} resize-y`}
            />
            <button
              onClick={() => (backend ? void readRequirementsLive() : readRequirements())}
              disabled={(!jdText.trim() && !jdFile) || busy}
              className="focus-ring mt-2 inline-flex items-center gap-1.5 rounded-md border border-honda-red/25 bg-honda-red-tint text-honda-red transition-colors hover:border-honda-red/45 hover:bg-honda-red-light px-3.5 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:border-cream-200 disabled:bg-cream-100 disabled:text-ink-300"
            >
              <Search size={14} /> Read requirements
            </button>
          </div>

          {/* JD requirement check — hidden entirely until the advert has been read */}
          <div ref={requirementsRef}>
            {analysis && (
              <div className="mt-5">
                <FieldLabel hint="Age, experience and qualification are checked in the advert. Anything not found must be entered by hand.">
                  Requirements found in the advert
                </FieldLabel>

                <div className="space-y-2">
                  {FIELD_ORDER.map((key) => {
                    const field = analysis[key];
                    const needsManual = !field.found;
                    const isEditing = editing[key];
                    const missing = needsManual && !manual[key].trim();
                    return (
                      <div
                        key={key}
                        className={`rounded-md border px-3 py-2.5 ${
                          missing
                            ? "border-warning/50 bg-warning-light/50"
                            : "border-cream-300 bg-white"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex min-w-0 items-start gap-2">
                            {field.found ? (
                              <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-success" />
                            ) : (
                              <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
                            )}
                            <div className="min-w-0">
                              <p className="text-sm font-bold text-ink-900">
                                {FIELD_LABELS[key]}
                              </p>
                              {field.found ? (
                                <p className="mt-0.5 text-xs leading-snug text-ink-600">
                                  “{field.jdValue}”
                                </p>
                              ) : (
                                <p className="mt-0.5 text-xs font-semibold text-warning">
                                  Not in the advert — type it in the box below
                                </p>
                              )}
                            </div>
                          </div>
                          {field.found && !isEditing && (
                            <button
                              onClick={() => setEditing((e) => ({ ...e, [key]: true }))}
                              className="focus-ring flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs font-bold text-honda-red hover:bg-honda-red-light"
                            >
                              <Pencil size={11} /> Edit
                            </button>
                          )}
                        </div>

                        {(needsManual || isEditing) && (
                          <div className="mt-2">
                            <input
                              value={manual[key]}
                              onChange={(e) => setManual((m) => ({ ...m, [key]: e.target.value }))}
                              placeholder={
                                key === "qualification"
                                  ? "e.g. Bachelor's in Mechanical Engineering"
                                  : key === "experience"
                                  ? "e.g. 2–4 years relevant experience"
                                  : "e.g. 22–30 years"
                              }
                              className={`${inputClass} ${
                                missing ? "border-2 border-warning bg-white" : ""
                              }`}
                              autoFocus={missing}
                            />
                            {field.found && (
                              <p className="mt-1 text-xs font-semibold text-honda-red">
                                A value entered here always overrides the advert.
                              </p>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Required skills */}
          <div className="mt-5">
            <FieldLabel hint="Filled in from the advert. Add or remove any before ranking.">
              Required skills
            </FieldLabel>
            <input
              value={skillInput}
              onChange={(e) => setSkillInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addSkill();
                }
              }}
              onBlur={addSkill}
              placeholder="Type a skill, press Enter"
              className={inputClass}
            />
            {skills.length === 0 ? (
              <p className="mt-1.5 text-xs italic text-ink-400">none yet</p>
            ) : (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {skills.map((s) => (
                  <span
                    key={s}
                    className="flex items-center gap-1 rounded-full bg-honda-red-light px-2.5 py-1 text-xs font-semibold text-honda-red-dark"
                  >
                    {s}
                    <button
                      onClick={() => setSkills((prev) => prev.filter((x) => x !== s))}
                      className="hover:text-honda-red"
                      aria-label={`Remove ${s}`}
                    >
                      <X size={11} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* CVs */}
          <div className="mt-5">
            <FieldLabel hint={`PDF, Word or text. Up to ${MAX_FILES} at once.`}>CVs</FieldLabel>
            <button
              onClick={() => cvInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragTarget("cv");
              }}
              onDragLeave={() => setDragTarget(null)}
              onDrop={(e) => {
                e.preventDefault();
                setDragTarget(null);
                handleCvFiles(Array.from(e.dataTransfer.files));
              }}
              className={`focus-ring flex w-full flex-col items-center gap-2 rounded-md border border-dashed px-4 py-6 text-center transition-colors ${
                dragTarget === "cv"
                  ? "border-honda-red bg-honda-red-tint"
                  : "border-honda-red/30 bg-honda-red-tint hover:border-honda-red/60 hover:bg-honda-red-light"
              }`}
            >
              <Upload size={20} className="text-honda-red" />
              <span className="text-sm font-semibold text-honda-red">
                Drop CVs here or click to choose
              </span>
            </button>
            <input
              ref={cvInputRef}
              type="file"
              multiple
              accept=".pdf,.doc,.docx,.txt"
              className="hidden"
              onChange={(e) => e.target.files && handleCvFiles(Array.from(e.target.files))}
            />

            {cvFiles.length > 0 && (
              <>
                <div className="mt-2 flex items-center justify-between text-xs">
                  <span className="font-semibold text-ink-700">
                    {cvFiles.length} file{cvFiles.length === 1 ? "" : "s"}
                  </span>
                  <button
                    onClick={() => setCvFiles([])}
                    className="focus-ring rounded px-1 font-semibold text-ink-400 hover:text-danger"
                  >
                    Remove all
                  </button>
                </div>
                <div className="mt-1.5 max-h-44 divide-y divide-cream-200 overflow-y-auto rounded-md border border-cream-200">
                  {cvFiles.map((f) => (
                    <div key={f.id} className="flex items-center justify-between gap-2 px-2.5 py-1.5">
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-ink-700">{f.name}</p>
                        {f.error && <p className="text-2xs text-danger">{f.error}</p>}
                      </div>
                      <div className="shrink-0">
                        {f.status === "processing" ? (
                          <Loader2 size={13} className="animate-spin text-honda-red" />
                        ) : f.status === "done" ? (
                          <CheckCircle2 size={13} className="text-success" />
                        ) : f.status === "failed" ? (
                          <XCircle size={13} className="text-danger" />
                        ) : (
                          <button
                            onClick={() => setCvFiles((p) => p.filter((x) => x.id !== f.id))}
                            className="focus-ring rounded p-0.5 text-ink-300 hover:text-danger"
                          >
                            <X size={12} />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* THE button */}
          <button
            onClick={handleRank}
            disabled={phase === "processing"}
            className="focus-ring mt-5 flex w-full items-center justify-center gap-2 rounded-md bg-honda-red px-4 py-3 text-md font-bold text-white transition-colors hover:bg-honda-red-dark active:bg-honda-red-darker disabled:bg-ink-300"
          >
            {phase === "processing" ? (
              <>
                <Loader2 size={17} className="animate-spin" /> Ranking…
              </>
            ) : (
              "Rank CVs"
            )}
          </button>
        </section>

        {/* ================= SHORTLIST ================= */}
        <section className="relative h-fit overflow-hidden rounded-xl2 border border-cream-200 bg-white shadow-card lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
          {/* The brand accent, on the panel that holds the answer. One rule,
              at the top of the one thing on this page the reader came for. */}
          <span
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 h-[3px]"
            style={{
              background:
                "linear-gradient(90deg, #CC0000 0%, #8C1A1E 42%, rgba(140,26,30,0) 100%)",
            }}
          />
          <div className="p-5 pt-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <PanelLabel>Shortlist</PanelLabel>
            {phase === "done" && candidates.length > 0 && (
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold text-ink-500">Show top</span>
                  <div className="flex rounded-md bg-honda-red-tint p-0.5 ring-1 ring-inset ring-honda-red/20">
                    {([5, 10, 20, 30] as const).map((n) => (
                      <button
                        key={n}
                        onClick={() => setTopN(n)}
                        className={`focus-ring rounded px-2.5 py-1 text-xs font-bold transition-colors ${
                          topN === n
                            ? "bg-honda-red text-white shadow-sm"
                            : "text-honda-red/70 hover:text-honda-red"
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold text-ink-500">Min</span>
                  <input
                    type="range"
                    min={0}
                    max={90}
                    step={5}
                    value={minScore}
                    onChange={(e) => setMinScore(Number(e.target.value))}
                    className="w-24 accent-honda-red"
                  />
                  <span className="w-8 text-xs font-bold text-ink-700">{minScore}%</span>
                </div>
                <button
                  onClick={exportCsv}
                  className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-honda-red/25 bg-honda-red-tint text-honda-red transition-colors hover:border-honda-red/45 hover:bg-honda-red-light px-3 py-1.5 text-xs font-semibold"
                >
                  <Download size={13} /> Export
                </button>
              </div>
            )}
          </div>

          {/* Blocked by validation — shown here because it's where the eye goes on Rank */}
          {phase === "idle" && errors.length > 0 && (
            <div className="min-h-[320px] px-2 py-6">
              <div className="mx-auto max-w-lg rounded-lg border border-danger/30 bg-danger-light px-5 py-5">
                <p className="flex items-center gap-2 text-md font-bold text-danger">
                  <AlertTriangle size={18} /> Can't rank yet
                </p>
                <p className="mt-1 text-sm text-danger/80">
                  {errors.length} thing{errors.length === 1 ? "" : "s"} to fix on the left before
                  the CVs can be scored.
                </p>
                <ul className="mt-3 space-y-2">
                  {errors.map((e, i) => (
                    <li
                      key={i}
                      className="flex gap-2 rounded-md bg-white/70 px-3 py-2 text-sm leading-snug text-ink-700"
                    >
                      <span className="font-bold text-danger">{i + 1}.</span>
                      <span>{e}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Idle */}
          {phase === "idle" && errors.length === 0 && (
            <div className="flex min-h-[320px] flex-col items-center justify-center px-6 text-center">
              <h3 className="text-lg font-bold text-ink-900">No shortlist yet</h3>
              <p className="mt-1.5 max-w-sm text-base text-ink-500">
                Set the role on the left, add CVs, then rank them.
              </p>
            </div>
          )}

          {/* Processing */}
          {phase === "processing" && (
            <div className="min-h-[320px] px-1 py-4">
              <div className="mx-auto max-w-md">
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="font-bold text-ink-800">
                    Reading {processedCount} of {cvFiles.length} CVs
                  </span>
                  <span className="font-semibold text-ink-500">{progressPct}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-cream-100">
                  <div
                    className="h-full rounded-full bg-honda-red transition-all duration-300"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <p className="mt-3 text-center text-xs text-ink-500">
                  Extracting qualifications, experience and skills, then scoring each CV against the
                  advert.
                </p>
              </div>
            </div>
          )}

          {/* Results */}
          {phase === "done" && (
            <>
              {/* Simulated results must never be mistaken for real ones.
                  The names, scores and CV filenames below are generated —
                  saying so here, next to the results, is the only place the
                  warning reliably gets seen. */}
              {!backend && (
                <div className="mb-3 rounded-md border border-warning/50 bg-warning-light px-3.5 py-3">
                  <p className="flex items-center gap-1.5 text-sm font-bold text-warning">
                    <AlertTriangle size={15} /> These are simulated results — not your CVs
                  </p>
                  <p className="mt-1 text-xs leading-snug text-ink-700">
                    The backend is not connected, so the names, scores and file names below
                    are invented demo data. Your uploaded CVs were never read. Start the
                    backend and press{" "}
                    <button
                      onClick={connectBackend}
                      className="focus-ring font-bold text-honda-red underline underline-offset-2"
                    >
                      retry
                    </button>{" "}
                    to rank the real files.
                  </p>
                </div>
              )}

              {failedCount > 0 && (
                <div className="mb-3 flex items-start gap-2 rounded-md bg-warning-light px-3 py-2 text-xs font-medium text-warning">
                  <RefreshCw size={13} className="mt-[2px] shrink-0" />
                  <span>
                    {rateLimitedCount > 0 && (
                      <>
                        {rateLimitedCount} CV{rateLimitedCount === 1 ? "" : "s"}{" "}
                        {rateLimitedCount === 1 ? "was" : "were"} left out because the AI
                        service hit its usage limit — {rateLimitedCount === 1 ? "the file is" : "the files are"}{" "}
                        fine. Click <strong>Rank CVs</strong> again in a minute to include{" "}
                        {rateLimitedCount === 1 ? "it" : "them"}.
                      </>
                    )}
                    {rateLimitedCount > 0 && unreadableCount > 0 && <br />}
                    {unreadableCount > 0 && (
                      <>
                        {unreadableCount} file{unreadableCount === 1 ? "" : "s"} could not be
                        read and {unreadableCount === 1 ? "was" : "were"} left out of the
                        ranking.
                      </>
                    )}
                  </span>
                </div>
              )}

              {/* What the run actually produced, before the list of who.
                  Median rather than mean: one 96 among a dozen 40s drags a
                  mean up and tells the reader the pool is fine when it is not.
                  "Needs review" is the flagged count — a number worth acting
                  on, so it is the one tile allowed to change colour. */}
              {candidates.length > 0 && (
                <div
                  className="mb-4 overflow-hidden rounded-xl2"
                  style={{
                    background:
                      "linear-gradient(112deg, #A82026 0%, #8C1A1E 34%, #6B1216 72%, #3E0B0D 100%)",
                  }}
                >
                  {/* Solid red, not four white cards. The summary and the list
                      were both white boxes, so the run's headline figures read
                      as a fifth and sixth row rather than as the thing the rows
                      are summarised by. A filled band separates the two without
                      a heading, and it is the one place on this page where the
                      brand colour can sit in quantity: nothing in here is a
                      score, so a red ground cannot be mistaken for a red band
                      on the scale. */}
                  <dl className="grid grid-cols-2 sm:grid-cols-4">
                    <StatTile
                      label="Ranked"
                      value={String(candidates.length)}
                      note={`of ${candidates.length + failedCount} CVs`}
                    />
                    <div className="border-white/15 sm:border-l">
                      <StatTile label="Top score" value={`${topScore}%`} note={topScoreBand} />
                    </div>
                    <div className="border-t border-white/15 sm:border-l sm:border-t-0">
                      <StatTile label="Median" value={`${medianScore}%`} note="across the pool" />
                    </div>
                    <div className="border-t border-white/15 sm:border-l sm:border-t-0">
                      <StatTile
                        label="Needs review"
                        value={String(flaggedCount)}
                        note={flaggedCount ? "low-confidence read" : "none flagged"}
                        alert={flaggedCount > 0}
                      />
                    </div>
                  </dl>
                </div>
              )}

              {visible.length === 0 ? (
                <div className="flex min-h-[280px] items-center justify-center text-base text-ink-500">
                  No candidates meet the current minimum score.
                </div>
              ) : (
                <ol className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  {visible.map((c, i) => {
                    const open = expandedId === c.id;
                    return (
                      <li key={c.id} className={open ? "xl:col-span-2" : undefined}>
                        <CandidateCard
                          candidate={c}
                          rank={i + 1}
                          role={jobTitle}
                          open={open}
                          copied={copiedId === c.id}
                          onToggle={() => setExpandedId(open ? null : c.id)}
                          onCopyEmail={() => void copyEmail(c)}
                        />

                        {open && (
                          // The reasons sit on a light card BELOW the black one,
                          // which is where the coloured meters can live safely.
                          <div className="animate-in mt-2 rounded-xl2 border border-cream-200 bg-white px-4 py-4 shadow-xs">
                            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                              <ReasonCard
                                title="Qualification"
                                value={c.scores.qualification}
                                detail={`${c.qualifications[0]?.degree ?? "Not stated"}. Required: ${requirementValue(
                                  "qualification"
                                )}`}
                              />
                              <ReasonCard
                                title="Experience"
                                value={c.scores.experience}
                                detail={`${c.relevantYears} relevant years. Required: ${requirementValue(
                                  "experience"
                                )}`}
                              />
                              <ReasonCard
                                title="JD & Skills"
                                value={c.scores.jdSkills}
                                detail={`Matched ${c.matchedSkills.length} of ${skills.length} required skills`}
                              />
                            </div>

                            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                              <div>
                                <p className="label mb-2">
                                  Work history
                                </p>
                                <div className="space-y-1.5">
                                  {c.experience.map((e, idx) => (
                                    <div
                                      key={idx}
                                      className="rounded-md border border-cream-300 bg-white px-2.5 py-2"
                                    >
                                      <div className="flex items-baseline justify-between gap-2">
                                        <p className="truncate text-sm font-semibold text-ink-800">
                                          {e.title}
                                        </p>
                                        <span className="shrink-0 text-2xs text-ink-400">
                                          {e.period}
                                        </span>
                                      </div>
                                      <p className="text-xs text-ink-500">
                                        {[e.employer, `${e.years} yrs`].filter(Boolean).join(" · ")}
                                      </p>
                                      <div className="mt-1.5 flex items-center gap-2">
                                        <span className="label">Relevance</span>
                                        <div className="h-1 w-16 overflow-hidden rounded-full bg-cream-200">
                                          <div
                                            className="h-full rounded-full bg-wine-600"
                                            style={{ width: `${Math.round(e.relevance * 100)}%` }}
                                          />
                                        </div>
                                        <span className="tnum text-2xs font-medium text-ink-500">
                                          {Math.round(e.relevance * 100)}%
                                        </span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>

                              <div>
                                <p className="label mb-2">
                                  Education
                                </p>
                                {c.qualifications.map((q, idx) => (
                                  <div
                                    key={idx}
                                    className="mb-3 rounded-md border border-cream-300 bg-white px-2.5 py-2"
                                  >
                                    <p className="text-sm font-semibold text-ink-800">{q.degree}</p>
                                    {(q.institution || q.year) && (
                                      <p className="text-xs text-ink-500">
                                        {[q.institution, q.year].filter(Boolean).join(" · ")}
                                      </p>
                                    )}
                                  </div>
                                ))}

                                <p className="label mb-2">
                                  Skills
                                </p>
                                <div className="flex flex-wrap gap-1">
                                  {c.matchedSkills.map((s) => (
                                    <span
                                      key={s}
                                      className="flex items-center gap-1 rounded-full bg-success-light px-2 py-0.5 text-2xs font-semibold text-success"
                                    >
                                      <CheckCircle2 size={10} /> {s}
                                    </span>
                                  ))}
                                  {c.missingSkills.map((s) => (
                                    <span
                                      key={s}
                                      className="flex items-center gap-1 rounded-full bg-danger-light px-2 py-0.5 text-2xs font-semibold text-danger"
                                    >
                                      <XCircle size={10} /> {s}
                                    </span>
                                  ))}
                                </div>

                                {/* Transferability reasoning — only the live
                                    backend produces this. It is the model
                                    explaining a judgement HR can challenge. */}
                                {(() => {
                                  const ac = apiCandidates.find(
                                    (a) => a.candidate_name === c.name
                                  );
                                  const transfers = (
                                    ac?.details?.jd_skills?.skill_matches ?? []
                                  ).filter((sm) => sm.method === "transferable" && sm.credit > 0);
                                  if (!transfers.length) return null;
                                  return (
                                    <div className="mt-3">
                                      <p className="label mb-2">
                                        Transferable skills
                                      </p>
                                      <div className="space-y-1.5">
                                        {transfers.map((t, ti) => (
                                          <div
                                            key={ti}
                                            className="rounded-md border border-warning/40 bg-warning-light/40 px-2.5 py-1.5"
                                          >
                                            <p className="text-xs font-bold text-ink-800">
                                              {t.required_skill} — {Math.round(t.credit * 100)}% credit
                                              {t.matched_skill ? ` via ${t.matched_skill}` : ""}
                                            </p>
                                            {t.reasoning && (
                                              <p className="mt-0.5 text-xs leading-snug text-ink-600">
                                                {t.reasoning}
                                              </p>
                                            )}
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  );
                                })()}
                              </div>
                            </div>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ol>
              )}

              <p className="mt-4 text-center text-xs text-ink-400">
                Ranking is advisory. Review each candidate's reasons before deciding.
              </p>
            </>
          )}
          </div>
        </section>
      </main>
    </div>
  );
};

const ReasonCard: React.FC<{ title: string; value: number; detail: string }> = ({
  title,
  value,
  detail,
}) => {
  const tone = scoreTone(value);
  return (
    // The band is carried by the meter under the number, not by colouring the
    // number — the same rule the shortlist rows follow, so a 74 does not look
    // like a different species of value in one panel and not the other.
    <div className="rounded-lg border border-cream-200 bg-white px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-2xs font-bold uppercase tracking-wide text-ink-500">{title}</p>
        <span className="tnum text-md font-semibold text-ink-900">{value}%</span>
      </div>
      <div className={`mt-2 h-1.5 overflow-hidden rounded-full ${tone.track}`}>
        <div
          className={`h-full rounded-full ${tone.bar}`}
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
      <p className="mt-2 text-xs leading-snug text-ink-500">{detail}</p>
    </div>
  );
};

export default Workspace;
