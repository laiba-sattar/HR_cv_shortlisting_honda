import React, { useState } from "react";
import { ChevronDown, Mail, Info } from "lucide-react";
import { Card, SectionTitle } from "../components/ui";

const faqs = [
  {
    q: "How is the final match score calculated?",
    a: "Each candidate gets three sub-scores — Qualification match, Relevant experience match, and JD & Skills match — each scored 0–100%. The final score is a simple equal-weighted average of the three (33% each). Every result page shows the breakdown, not just the final number, so you can see exactly what a candidate scored well or poorly on.",
  },
  {
    q: "What counts as \"relevant\" experience, not just total years?",
    a: "The system doesn't just add up years of work. Each past role is weighted by how closely its description matches the job description — so five years in a closely related role counts far more than five years in an unrelated one. The Candidate Detail page shows this per-role relevance percentage.",
  },
  {
    q: "What happens if the JD doesn't mention age, experience, or qualification?",
    a: "The JD Analysis page checks for all three fields. Any field not found in the JD becomes a required manual entry before you can proceed to ranking. If a field is found but you also enter a manual value, your manually entered value always takes priority over what was detected in the JD.",
  },
  {
    q: "Can it reject or shortlist a candidate on its own?",
    a: "No. This is a decision-support tool — it ranks and explains. It never automatically advances or rejects anyone. The optional \"Shortlisted / Not shortlisted / Undecided\" tag on the Candidate Detail page is just a private note for your own tracking; your organization's actual hiring workflow continues wherever it already lives.",
  },
  {
    q: "Why did a CV fail to process?",
    a: "Usually a scanned image with text the system couldn't confidently read, or a corrupted/password-protected file. Failed files are flagged individually on the Processing Status page and can be retried without restarting the rest of the batch.",
  },
  {
    q: "Who can see the audit log?",
    a: "Admin-role users only, via the Admin Panel. It records every scoring decision and every JD-vs-manual field resolution, timestamped, for compliance review.",
  },
];

const Help: React.FC = () => {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <SectionTitle
        title="Help & FAQ"
        subtitle="How scoring works, in plain language, plus where to go if something looks wrong."
      />

      <Card className="flex items-start gap-3 border-honda-red/20 bg-honda-red-tint/40">
        <Info size={18} className="mt-0.5 shrink-0 text-honda-red" />
        <p className="text-sm text-ink-700">
          This tool ranks and explains — it does not make hiring decisions. A human reviewer always
          makes the final call, using the full score breakdown provided on each candidate.
        </p>
      </Card>

      <Card padded={false}>
        <div className="divide-y divide-cream-200">
          {faqs.map((f, i) => (
            <div key={i}>
              <button
                onClick={() => setOpen(open === i ? null : i)}
                className="focus-ring flex w-full items-center justify-between gap-4 px-6 py-4 text-left"
              >
                <span className="text-sm font-semibold text-ink-900">{f.q}</span>
                <ChevronDown
                  size={17}
                  className={`shrink-0 text-ink-400 transition-transform ${open === i ? "rotate-180" : ""}`}
                />
              </button>
              {open === i && <p className="px-6 pb-4 text-sm leading-relaxed text-ink-600">{f.a}</p>}
            </div>
          ))}
        </div>
      </Card>

      <Card className="flex flex-col items-center gap-2 py-8 text-center">
        <Mail size={20} className="text-honda-red" />
        <p className="text-sm font-semibold text-ink-800">Need more help?</p>
        <p className="text-xs text-ink-500">
          Contact your IT administrator or the HR systems support team.
        </p>
      </Card>
    </div>
  );
};

export default Help;
