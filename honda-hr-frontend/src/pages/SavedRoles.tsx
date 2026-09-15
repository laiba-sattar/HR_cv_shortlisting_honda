import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  FilePlus2,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardHead,
  EmptyState,
  IconButton,
  Modal,
  SectionTitle,
} from "../components/ui";
import * as api from "../api";
import { whenText } from "../utils/when";

/**
 * Past rankings.
 *
 * Read from the server, not from anything this browser stored. A history page
 * showing sample rows would be the same trap the administration page used to
 * be: it looks like a record, so it gets treated as one.
 */

type RunRow = {
  id: string;
  title: string;
  status: string;
  created_at: string;
  created_by: string;
  version: number;
  top_n: number;
  candidate_count: number;
  required_skills: string[];
};

const STATUS_TONE: Record<string, "green" | "amber" | "red" | "gray"> = {
  completed: "green",
  processing: "amber",
  failed: "red",
};

/* The database's own words, written for a reader. Printing the column value
   raw put a lowercase "completed" in a row of otherwise composed type. */
const STATUS_LABELS: Record<string, string> = {
  completed: "Completed",
  processing: "Running",
  failed: "Failed",
};

const SavedRoles: React.FC = () => {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { runs } = (await api.listRuns()) as unknown as { runs: RunRow[] };
      setRuns(runs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load past rankings.");
      setRuns([]);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(
    () =>
      (runs ?? []).filter((r) =>
        r.title.toLowerCase().includes(query.trim().toLowerCase())
      ),
    [runs, query]
  );

  const remove = async () => {
    if (!confirmId) return;
    setBusy(true);
    try {
      await api.deleteRun(confirmId);
      setConfirmId(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete that ranking.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-7">
      <SectionTitle
        eyebrow="History"
        title="Past rankings"
        subtitle="Every run is kept in full — the requirements that applied, the scores, and the model versions that produced them."
        action={
          <Button icon={<FilePlus2 size={15} />} onClick={() => navigate("/")}>
            New ranking
          </Button>
        }
      />

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-danger/15 bg-danger-light px-4 py-3 text-sm font-medium text-danger">
          <AlertTriangle size={15} className="mt-px shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <Card padded={false}>
        <CardHead
          title={runs === null ? "Loading…" : `${runs.length} recorded`}
          action={
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search
                  size={14}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400"
                />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search job title"
                  className="field field-sm w-56 pl-8"
                />
              </div>
              <IconButton label="Refresh" onClick={load}>
                <RefreshCw size={14} />
              </IconButton>
            </div>
          }
        />

        {runs === null ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={18} className="animate-spin text-honda-red" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title={runs.length === 0 ? "Nothing ranked yet" : "No match"}
              description={
                runs.length === 0
                  ? "Rankings appear here as soon as you run one."
                  : "Try a different search."
              }
              action={
                runs.length === 0 ? (
                  <Button onClick={() => navigate("/")}>Go to the workspace</Button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left">
              <thead>
                <tr className="border-b border-cream-200">
                  <th className="label px-6 py-3">Role</th>
                  <th className="label px-3 py-3">Run</th>
                  <th className="label px-3 py-3">By</th>
                  <th className="label px-3 py-3 text-right">Candidates</th>
                  <th className="label px-3 py-3">Status</th>
                  <th className="label px-6 py-3 text-right">Delete</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-cream-200">
                {filtered.map((r) => (
                  <tr key={r.id} className="group transition-colors hover:bg-cream-50">
                    <td className="px-6 py-3.5">
                      <button
                        onClick={() => navigate(`/?run=${r.id}`)}
                        className="focus-ring rounded text-left text-base font-semibold text-ink-900 hover:text-honda-red"
                      >
                        {r.title || "Untitled role"}
                      </button>
                      {r.required_skills?.length > 0 && (
                        <p className="mt-0.5 truncate text-xs text-ink-400">
                          {r.required_skills.slice(0, 4).join(" · ")}
                          {r.required_skills.length > 4 && " …"}
                        </p>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3.5 text-sm text-ink-500">
                      {whenText(r.created_at)}
                    </td>
                    <td className="px-3 py-3.5 text-sm text-ink-600">{r.created_by}</td>
                    <td className="tnum px-3 py-3.5 text-right text-base font-semibold text-ink-900">
                      {r.candidate_count}
                    </td>
                    <td className="px-3 py-3.5">
                      <Badge tone={STATUS_TONE[r.status] ?? "gray"}>
                        {STATUS_LABELS[r.status] ?? r.status}
                      </Badge>
                    </td>
                    <td className="px-6 py-3.5 text-right">
                      <IconButton
                        label={`Delete ${r.title}`}
                        onClick={() => setConfirmId(r.id)}
                        className="opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100 hover:border-danger hover:text-danger"
                      >
                        <Trash2 size={14} />
                      </IconButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal
        open={confirmId !== null}
        onClose={() => setConfirmId(null)}
        title="Delete this ranking?"
        footer={
          <>
            <Button variant="outline" onClick={() => setConfirmId(null)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={remove} disabled={busy}>
              {busy ? "Deleting…" : "Delete"}
            </Button>
          </>
        }
      >
        The scores, the requirements that applied and the uploaded CVs all go
        with it. Nothing about this run can be reconstructed afterwards.
      </Modal>
    </div>
  );
};

export default SavedRoles;
