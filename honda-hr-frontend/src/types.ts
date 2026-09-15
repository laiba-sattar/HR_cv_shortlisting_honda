export type FieldStatus = {
  found: boolean;
  jdValue?: string;
  manualValue?: string;
};

export type JDProfile = {
  fileName: string;
  uploadedAt: string;
  detectedSkills: string[];
  age: FieldStatus;
  experience: FieldStatus;
  qualification: FieldStatus;
};

export type QualificationEntry = {
  degree: string;
  field: string;
  institution: string;
  year: string;
};

export type ExperienceEntry = {
  title: string;
  employer: string;
  period: string;
  years: number;
  description: string;
  relevance: number; // 0-1
};

export type CandidateStatus = "Shortlisted" | "Not shortlisted" | "Undecided";

export type Candidate = {
  id: string;
  name: string;
  initials: string;
  email: string;
  phone: string;
  cvFileName: string;
  age?: number;
  qualifications: QualificationEntry[];
  experience: ExperienceEntry[];
  skills: string[];
  matchedSkills: string[];
  missingSkills: string[];
  scores: {
    qualification: number;
    experience: number;
    jdSkills: number;
    final: number;
  };
  relevantYears: number;
  status: CandidateStatus;
  notes: string;
  flagged?: boolean; // low-confidence extraction
};

export type JobStatus =
  | "Draft"
  | "Ready to Rank"
  | "Processing"
  | "Completed";

export type FileItem = {
  id: string;
  name: string;
  sizeKb: number;
  status: "queued" | "processing" | "done" | "failed";
  error?: string;
};

export type JobRun = {
  id: string;
  title: string;
  status: JobStatus;
  createdAt: string;
  createdBy: string;
  requiredSkills: string[];
  jd: JDProfile;
  files: FileItem[];
  candidates: Candidate[];
  topN: 5 | 10 | 20 | 30;
  version: number;
};
