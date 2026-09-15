import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { JobRun } from "../types";
import { seedJobs } from "../data/seed";

type AppState = {
  jobs: JobRun[];
};

type AppContextValue = AppState & {
  addJob: (job: JobRun) => void;
  updateJob: (id: string, patch: Partial<JobRun>) => void;
  getJob: (id: string) => JobRun | undefined;
  removeJob: (id: string) => void;
};

const AppContext = createContext<AppContextValue | null>(null);

const STORAGE_KEY = "honda-hr-cv-shortlisting.jobs.v1";

function loadJobs(): JobRun[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as JobRun[];
  } catch {
    // fall through to seed data
  }
  return seedJobs;
}

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [jobs, setJobs] = useState<JobRun[]>(() => loadJobs());

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
    } catch {
      // storage unavailable — non-fatal for the demo
    }
  }, [jobs]);

  const addJob = (job: JobRun) => setJobs((prev) => [job, ...prev]);

  const updateJob = (id: string, patch: Partial<JobRun>) =>
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, ...patch } : j)));

  const removeJob = (id: string) => setJobs((prev) => prev.filter((j) => j.id !== id));

  const getJob = (id: string) => jobs.find((j) => j.id === id);

  // Identity lives in AuthContext and comes from the server. It used to be a
  // constant here, which is why every run in the audit log carried the same
  // name whoever ran it.
  const value = useMemo(
    () => ({ jobs, addJob, updateJob, removeJob, getJob }),
    [jobs]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
