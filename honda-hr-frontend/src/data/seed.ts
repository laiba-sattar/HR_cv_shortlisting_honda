import type { JobRun } from "../types";
import { generateCandidates } from "./generate";

const skillSetA = [
  "AutoCAD", "SolidWorks", "GD&T", "Six Sigma", "Quality Control", "Lean Manufacturing",
];
const skillSetB = [
  "Production Planning", "Lean Manufacturing", "5S Methodology", "MS Excel", "Kaizen",
];
const skillSetC = ["MATLAB", "PLC Programming", "Vehicle Dynamics", "CATIA"];

export const seedJobs: JobRun[] = [
  {
    id: "job-1001",
    title: "Mechanical Design Engineer",
    status: "Completed",
    createdAt: "2026-08-10T09:20:00+05:00",
    createdBy: "Laiba Sattar",
    requiredSkills: skillSetA,
    jd: {
      fileName: "JD_Mechanical_Design_Engineer.pdf",
      uploadedAt: "2026-08-10T09:18:00+05:00",
      detectedSkills: ["AutoCAD", "SolidWorks", "GD&T", "Product Design"],
      age: { found: true, jdValue: "22–30 years" },
      experience: { found: true, jdValue: "2–4 years relevant experience" },
      qualification: { found: true, jdValue: "Bachelor's in Mechanical Engineering" },
    },
    files: [],
    candidates: generateCandidates(23, skillSetA),
    topN: 10,
    version: 1,
  },
  {
    id: "job-1002",
    title: "Production Engineer — Internship",
    status: "Completed",
    createdAt: "2026-08-05T14:05:00+05:00",
    createdBy: "Laiba Sattar",
    requiredSkills: skillSetB,
    jd: {
      fileName: "JD_Production_Engineer_Intern.docx",
      uploadedAt: "2026-08-05T14:00:00+05:00",
      detectedSkills: ["Production Planning", "Lean Manufacturing", "MS Excel"],
      age: { found: false },
      experience: { found: true, jdValue: "0–1 years (fresh graduate / internship)" },
      qualification: { found: true, jdValue: "Bachelor's in Industrial or Mechanical Engineering" },
    },
    files: [],
    candidates: generateCandidates(41, skillSetB),
    topN: 20,
    version: 1,
  },
  {
    id: "job-1003",
    title: "R&D Engineer — Powertrain",
    status: "Draft",
    createdAt: "2026-08-20T11:40:00+05:00",
    createdBy: "Laiba Sattar",
    requiredSkills: skillSetC,
    jd: {
      fileName: "JD_RnD_Powertrain.pdf",
      uploadedAt: "2026-08-20T11:38:00+05:00",
      detectedSkills: ["MATLAB", "Vehicle Dynamics"],
      age: { found: false },
      experience: { found: false },
      qualification: { found: true, jdValue: "Bachelor's/Master's in Mechanical or Mechatronics Engineering" },
    },
    files: [],
    candidates: [],
    topN: 10,
    version: 1,
  },
];
