import type { Candidate, ExperienceEntry, QualificationEntry } from "../types";
import {
  DEGREES,
  EMPLOYERS,
  FIRST_NAMES,
  INSTITUTIONS,
  LAST_NAMES,
  ROLE_TITLES,
  SKILL_POOL,
  pick,
  pickN,
  randInt,
} from "./pools";

function clamp(n: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, n));
}

let uid = 1000;
function nextId(prefix: string) {
  uid += 1;
  return `${prefix}-${uid}`;
}

export function generateCandidate(requiredSkills: string[]): Candidate {
  const first = pick(FIRST_NAMES);
  const last = pick(LAST_NAMES);
  const name = `${first} ${last}`;
  const initials = `${first[0]}${last[0]}`;

  const degreeInfo = pick(DEGREES);
  const qualifications: QualificationEntry[] = [
    {
      degree: degreeInfo.degree,
      field: degreeInfo.field,
      institution: pick(INSTITUTIONS),
      year: String(randInt(2016, 2024)),
    },
  ];

  const numRoles = randInt(1, 3);
  const experience: ExperienceEntry[] = Array.from({ length: numRoles }).map(() => {
    const years = Number((Math.random() * 3.5 + 0.4).toFixed(1));
    const relevance = Number(Math.random().toFixed(2));
    return {
      title: pick(ROLE_TITLES),
      employer: pick(EMPLOYERS),
      period: `${randInt(2018, 2023)} – ${randInt(2022, 2025)}`,
      years,
      relevance,
      description:
        "Supported production-line process improvements, quality checks, and cross-functional coordination on assigned projects.",
    };
  });
  const relevantYears = Number(
    experience.reduce((sum, e) => sum + e.years * e.relevance, 0).toFixed(1)
  );

  const candidateSkills = new Set<string>(pickN(SKILL_POOL, randInt(5, 9)));
  const matchedSkills = requiredSkills.filter((s) =>
    [...candidateSkills].some((cs) => cs.toLowerCase() === s.toLowerCase())
  );
  // ensure some overlap so the demo looks plausible
  if (matchedSkills.length === 0 && requiredSkills.length > 0) {
    const forced = pick(requiredSkills);
    candidateSkills.add(forced);
    matchedSkills.push(forced);
  }
  const missingSkills = requiredSkills.filter(
    (s) => !matchedSkills.some((m) => m.toLowerCase() === s.toLowerCase())
  );

  const qualificationScore = clamp(randInt(45, 97));
  const experienceScore = clamp(randInt(30, 96));
  const skillsBase =
    requiredSkills.length === 0
      ? randInt(50, 90)
      : (matchedSkills.length / requiredSkills.length) * 100;
  const jdSkillsScore = clamp(Math.round(skillsBase + randInt(-8, 8)));
  const final = Math.round((qualificationScore + experienceScore + jdSkillsScore) / 3);

  return {
    id: nextId("cand"),
    name,
    initials,
    email: `${first.toLowerCase()}.${last.toLowerCase()}@example.com`,
    phone: `+92 3${randInt(0, 9)}${randInt(0, 9)} ${randInt(1000000, 9999999)}`,
    cvFileName: `${first}_${last}_CV.pdf`,
    age: randInt(22, 34),
    qualifications,
    experience,
    skills: [...candidateSkills],
    matchedSkills,
    missingSkills,
    relevantYears,
    scores: {
      qualification: qualificationScore,
      experience: experienceScore,
      jdSkills: jdSkillsScore,
      final,
    },
    status: "Undecided",
    notes: "",
    flagged: Math.random() < 0.12,
  };
}

export function generateCandidates(count: number, requiredSkills: string[]): Candidate[] {
  const list = Array.from({ length: count }).map(() => generateCandidate(requiredSkills));
  return list.sort((a, b) => b.scores.final - a.scores.final);
}

export { nextId };
export const totalYearsOf = (exp: ExperienceEntry[]) =>
  Number(exp.reduce((s, e) => s + e.years, 0).toFixed(1));
