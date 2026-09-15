import type { JDProfile } from "../types";
import { SKILL_POOL } from "../data/pools";

// ---------------------------------------------------------------------------
// Demo-mode JD analysis (used only when the backend is unreachable).
//
// The three-field check is a PRESENCE question, so it has a reliable
// deterministic answer from the text itself — the same patterns the backend
// uses in cv_ranker/jd_rules.py, kept in sync deliberately.
//
// Important: this never guesses. If the advert text is not available (a PDF or
// Word file was uploaded, which the browser cannot read without the backend
// parser), every field is reported as NOT FOUND so the user is asked to enter
// it. Claiming a requirement was found without having read it would be worse
// than asking — it would silently screen candidates against a rule nobody set.
// ---------------------------------------------------------------------------

const AGE_PATTERNS: RegExp[] = [
  /\bage\s*(?:limit|requirement|range|criteria|bracket)?\s*[:\-–]\s*[^\n]{0,60}/i,
  /\b\d{2}\s*(?:-|–|—|to)\s*\d{2}\s*years?\s*(?:of\s*age|old)\b/i,
  /\bbetween\s+\d{2}\s+and\s+\d{2}\s+years\s+of\s+age\b/i,
  /\b(?:max(?:imum)?|min(?:imum)?|under|below|above|over)\s+age\b[^\n]{0,50}/i,
  /\bnot\s+(?:more|older|younger)\s+than\s+\d{2}\s*(?:years)?\b/i,
  /\byears?\s+of\s+age\b/i,
  /\bdate\s+of\s+birth\b/i,
];

const EXPERIENCE_PATTERNS: RegExp[] = [
  /\bexperience\s*[:\-–]\s*[^\n]{0,80}/i,
  /\b\d+\s*(?:\+|plus)?\s*(?:-|–|—|to)?\s*\d*\s*years?['’]?\s*(?:of\s+)?(?:relevant\s+|professional\s+|work\s+|industry\s+|post[- ]qualification\s+)?experience\b/i,
  /\b(?:minimum|at\s+least|no\s+less\s+than)\s+\d+\s+years?\b[^\n]{0,50}/i,
  /\bfresh\s+graduates?\b[^\n]{0,40}/i,
  /\bno\s+prior\s+experience\b[^\n]{0,40}/i,
  /\bentry[- ]level\b/i,
  /\bexperience\b/i,
];

const QUALIFICATION_PATTERNS: RegExp[] = [
  /\b(?:qualification|education|academic\s+requirement)s?\s*[:\-–]\s*[^\n]{0,100}/i,
  /\b(?:bachelor|master|doctorate|phd)[^\n]{0,80}/i,
  /\b(?:bs|ms|b\.?sc|m\.?sc|b\.?e|m\.?e|b\.?tech|m\.?tech|bba|mba|acca|acma|ca|cfa|cima|icma)\b[^\n]{0,80}/i,
  /\bdegree\s+in\b[^\n]{0,60}/i,
  /\bdiploma\s+in\b[^\n]{0,60}/i,
  /\bgraduate\s+(?:in|of|from)\b[^\n]{0,60}/i,
];

function clean(s: string): string {
  return s
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[•\-*\d.]+\s*/, "")
    .replace(/[ .,;:]+$/, "");
}

/** Returns the line containing the first match, as quotable evidence. */
function findSnippet(text: string, patterns: RegExp[]): string | undefined {
  for (const pattern of patterns) {
    const m = pattern.exec(text);
    if (!m) continue;
    const lineStart = text.lastIndexOf("\n", m.index) + 1;
    let lineEnd = text.indexOf("\n", m.index + m[0].length);
    if (lineEnd === -1) lineEnd = text.length;
    const snippet = clean(text.slice(lineStart, lineEnd)) || clean(m[0]);
    return snippet.length > 200 ? snippet.slice(0, 197) + "…" : snippet;
  }
  return undefined;
}

/** Pulls known skills out of the advert so "Read requirements" pre-fills them. */
export function extractSkills(text: string): string[] {
  if (!text.trim()) return [];
  return SKILL_POOL.filter((skill) => {
    const escaped = skill.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(^|[^A-Za-z])${escaped}([^A-Za-z]|$)`, "i").test(text);
  });
}

const NOT_FOUND = { found: false, jdValue: undefined };

export function analyzeJD(_title: string, text: string, fileName: string): JDProfile {
  const hasText = text.trim().length > 20;

  // No readable text — report nothing as found rather than inventing an answer.
  if (!hasText) {
    return {
      fileName: fileName || "uploaded file",
      uploadedAt: new Date().toISOString(),
      detectedSkills: [],
      qualification: { ...NOT_FOUND },
      experience: { ...NOT_FOUND },
      age: { ...NOT_FOUND },
    };
  }

  const qualification = findSnippet(text, QUALIFICATION_PATTERNS);
  const experience = findSnippet(text, EXPERIENCE_PATTERNS);
  const age = findSnippet(text, AGE_PATTERNS);

  return {
    fileName: fileName || "pasted text",
    uploadedAt: new Date().toISOString(),
    detectedSkills: extractSkills(text),
    qualification: { found: !!qualification, jdValue: qualification },
    experience: { found: !!experience, jdValue: experience },
    age: { found: !!age, jdValue: age },
  };
}

export function simulateFileOutcome(): { failed: boolean; reason?: string } {
  const roll = Math.random();
  if (roll < 0.05) return { failed: true, reason: "Unreadable scan — OCR confidence too low" };
  if (roll < 0.08) return { failed: true, reason: "Corrupted or password-protected file" };
  return { failed: false };
}
