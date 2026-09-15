// Realistic-sounding pools used only to generate demo / mock data client-side.
// No real candidate data is used anywhere in this frontend.

export const FIRST_NAMES = [
  "Ahmed", "Bilal", "Sara", "Ayesha", "Hamza", "Fatima", "Usman", "Zainab",
  "Ali", "Mariam", "Hassan", "Sana", "Omar", "Iqra", "Tariq", "Nida",
  "Farhan", "Hira", "Kamran", "Rabia", "Salman", "Amna", "Waqas", "Noor",
  "Adeel", "Sadia", "Imran", "Mahnoor", "Danish", "Areeba",
];
export const LAST_NAMES = [
  "Khan", "Malik", "Siddiqui", "Raza", "Iqbal", "Shaikh", "Baig", "Farooq",
  "Chaudhry", "Abbasi", "Qureshi", "Javed", "Butt", "Aslam", "Rehman",
  "Nawaz", "Hussain", "Anwar", "Sheikh", "Yousuf",
];

export const INSTITUTIONS = [
  "NUST, Islamabad", "UET Lahore", "GIK Institute", "FAST-NUCES, Karachi",
  "PIEAS, Islamabad", "NED University, Karachi", "University of Punjab, Lahore",
  "Mehran UET, Jamshoro", "COMSATS, Lahore", "Air University, Islamabad",
];

export const DEGREES = [
  { degree: "BSc Mechanical Engineering", field: "Mechanical Engineering" },
  { degree: "BSc Automotive Engineering", field: "Automotive Engineering" },
  { degree: "BSc Industrial Engineering", field: "Industrial Engineering" },
  { degree: "BSc Electrical Engineering", field: "Electrical Engineering" },
  { degree: "BBA (Hons)", field: "Business Administration" },
  { degree: "BSc Mechatronics Engineering", field: "Mechatronics Engineering" },
  { degree: "MSc Mechanical Engineering", field: "Mechanical Engineering" },
  { degree: "BSc Manufacturing Engineering", field: "Manufacturing Engineering" },
];

export const EMPLOYERS = [
  "Indus Motor Company", "Pak Suzuki Motor Co.", "Millat Tractors Ltd.",
  "Atlas Honda Ltd.", "Ghandhara Industries", "Master Motor Corporation",
  "Descon Engineering", "Engro Corporation", "Nishat Chunian Group",
  "Siemens Pakistan", "Fauji Fertilizer Company", "Interloop Limited",
];

export const ROLE_TITLES = [
  "Production Engineer", "Quality Assurance Intern", "Mechanical Design Engineer",
  "Manufacturing Trainee", "Process Engineer", "Maintenance Engineer",
  "Supply Chain Intern", "Junior Design Engineer", "Plant Engineer",
  "R&D Engineer Intern",
];

export const SKILL_POOL = [
  "AutoCAD", "SolidWorks", "CATIA", "Six Sigma", "Lean Manufacturing",
  "GD&T", "Quality Control", "Production Planning", "MS Excel",
  "Supply Chain Management", "Project Management", "CNC Machining",
  "Root Cause Analysis", "ISO 9001", "PLC Programming", "MATLAB",
  "Vehicle Dynamics", "Thermodynamics", "Kaizen", "5S Methodology",
  "Cost Analysis", "Team Leadership", "Technical Documentation",
];

export function pick<T>(arr: T[], seedOffset = 0): T {
  const idx = Math.floor(Math.random() * arr.length + seedOffset) % arr.length;
  return arr[idx];
}

export function pickN<T>(arr: T[], n: number): T[] {
  const shuffled = [...arr].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, Math.min(n, arr.length));
}

export function randInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}
