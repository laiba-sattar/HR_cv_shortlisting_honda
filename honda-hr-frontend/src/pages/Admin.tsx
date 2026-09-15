import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Search, UserPlus } from "lucide-react";
import { Badge, Button, Card, SectionTitle } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import * as api from "../api";
import { whenTextExact } from "../utils/when";

/**
 * Managing access, and reading the record of what was done.
 *
 * Everything here is read from the server. An access page showing sample data
 * would be worse than no page at all: an administrator could switch somebody
 * off, see the row change, and believe access was withdrawn when nothing had
 * happened.
 */

type AuditEntry = {
  at: string;
  actor: string;
  action: string;
  run_id: string | null;
  detail: string | null;
};

const ACTION_LABELS: Record<string, string> = {
  signed_in: "Signed in",
  // Every Firebase route gets its own line. "Signed in" that cannot say how
  // is a weaker record: these fail in different ways, and the log is read
  // months later by somebody asking exactly that question.
  signed_in_with_google: "Signed in with Google",
  signed_in_with_password: "Signed in with a password",
  signed_in_by_email_link: "Signed in by email link",
  signed_in_by_firebase: "Signed in through Firebase",
  signed_in_by_phone: "Signed in by phone",
  signed_out: "Signed out",
  login_code_sent: "Sign-in code sent",
  analyze_jd: "Analysed a job advert",
  start_ranking: "Started a ranking",
  ranking_completed: "Ranking completed",
  ranking_failed: "Ranking failed",
  delete_run: "Deleted a ranking",
  password_set: "Set a password",
  password_failed: "Wrong password",
  user_added: "Granted access",
  user_updated: "Updated a user",
  user_activated: "Re-enabled access",
  user_deactivated: "Withdrew access",
};

const label = (action: string) =>
  ACTION_LABELS[action] ?? action.replace(/_/g, " ");

/** How many audit lines to fetch at a time. */
const AUDIT_PAGE = 200;

const Admin: React.FC = () => {
  const { user: me } = useAuth();

  const [users, setUsers] = useState<api.ManagedUser[] | null>(null);
  const [audit, setAudit] = useState<AuditEntry[] | null>(null);
  // How many entries EXIST, which is not the same as how many were fetched.
  const [auditTotal, setAuditTotal] = useState<number | null>(null);
  const [auditLimit, setAuditLimit] = useState(AUDIT_PAGE);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newRole, setNewRole] = useState<"hr" | "admin">("hr");
  const [newPhone, setNewPhone] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      const [u, a] = await Promise.all([
        api.listManagedUsers(),
        api.getAudit(auditLimit) as Promise<{
          entries: AuditEntry[];
          total?: number;
        }>,
      ]);
      setUsers(u.users);
      setAudit(a.entries);
      setAuditTotal(a.total ?? a.entries.length);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this page.");
    }
  }, [auditLimit]);

  useEffect(() => {
    load();
  }, [load]);

  const addUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy("add");
    setError(null);
    try {
      await api.addManagedUser({
        email: newEmail.trim(),
        name: newName.trim() || newEmail.trim().split("@")[0],
        role: newRole,
        phone: newPhone.trim() || undefined,
      });
      setNewEmail("");
      setNewName("");
      setNewPhone("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add that person.");
    } finally {
      setBusy(null);
    }
  };

  const toggle = async (u: api.ManagedUser) => {
    setBusy(u.email);
    setError(null);
    try {
      await api.setManagedUserActive(u.email, !u.active);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not change that account.");
    } finally {
      setBusy(null);
    }
  };

  const visible = (users ?? []).filter(
    (u) =>
      u.name.toLowerCase().includes(query.toLowerCase()) ||
      u.email.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="space-y-8">
      <SectionTitle
        title="Administration"
        subtitle="Who may sign in, and the record of what has been done."
      />

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-danger-light px-4 py-3 text-sm font-medium text-danger">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* ---------------- who may sign in ---------------- */}
      <Card padded={false}>
        <div className="flex flex-col justify-between gap-3 border-b border-cream-200 px-6 py-4 sm:flex-row sm:items-center">
          <div>
            <h3 className="text-sm font-bold text-ink-900">Who may sign in</h3>
            <p className="text-xs text-ink-500">
              Both email and phone sign-in check this list. Access is switched
              off, never deleted, so past rankings keep naming who ran them.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-400" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search"
                className="field field-sm w-48 pl-8"
              />
            </div>
            <button
              onClick={load}
              title="Refresh"
              className="focus-ring rounded-md border border-cream-300 p-1.5 text-ink-500 hover:text-honda-red"
            >
              <RefreshCw size={14} />
            </button>
          </div>
        </div>

        {users === null ? (
          <Loading />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-cream-200 text-left text-xs uppercase tracking-wider text-ink-400">
                  <th className="px-6 py-2.5 font-semibold">Name</th>
                  <th className="px-6 py-2.5 font-semibold">Email</th>
                  <th className="px-6 py-2.5 font-semibold">Phone</th>
                  <th className="px-6 py-2.5 font-semibold">Role</th>
                  <th className="px-6 py-2.5 text-right font-semibold">Access</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((u) => (
                  <tr key={u.email} className="border-b border-ink-50 last:border-0">
                    <td className="px-6 py-3 font-semibold text-ink-900">
                      {u.name}
                      {u.email === me?.email && (
                        <span className="ml-2 text-xs font-normal text-ink-400">you</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-ink-600">{u.email}</td>
                    <td className="px-6 py-3 font-mono text-xs text-ink-500">
                      {u.phone || "—"}
                    </td>
                    <td className="px-6 py-3">
                      <Badge tone={u.role === "admin" ? "red" : "gray"}>
                        {u.role === "admin" ? "Administrator" : "HR"}
                      </Badge>
                    </td>
                    <td className="px-6 py-3 text-right">
                      {u.email === me?.email ? (
                        <span className="text-xs text-ink-400">—</span>
                      ) : (
                        <button
                          onClick={() => toggle(u)}
                          disabled={busy === u.email}
                          className={`focus-ring rounded-md border px-2.5 py-1 text-xs font-semibold transition-colors ${
                            u.active
                              ? // Withdrawing access removes somebody, so this
                                // one stays in the danger colour rather than
                                // the brand tint — it is the one button on the
                                // page whose colour is a warning, not a style.
                                "border-danger/30 bg-danger-light text-danger hover:border-danger/60"
                              : "border-success/40 bg-success-light text-success hover:border-success"
                          }`}
                        >
                          {busy === u.email ? "…" : u.active ? "Withdraw" : "Restore"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {visible.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-center text-ink-400">
                      Nobody matches that search.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* add somebody */}
        <form
          onSubmit={addUser}
          className="flex flex-col gap-2 border-t border-cream-200 bg-cream-50/70 px-6 py-4 sm:flex-row sm:items-center"
        >
          <input
            type="email"
            required
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="name@company.com"
            className="field field-sm flex-1"
          />
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Full name"
            className="field field-sm w-full sm:w-44"
          />
          <input
            value={newPhone}
            onChange={(e) => setNewPhone(e.target.value)}
            placeholder="Phone (optional)"
            className="field field-sm w-full sm:w-40"
          />
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as "hr" | "admin")}
            className="field field-sm w-auto"
          >
            <option value="hr">HR</option>
            <option value="admin">Administrator</option>
          </select>
          <Button
            type="submit"
            disabled={busy === "add" || !newEmail.trim()}
            icon={
              busy === "add" ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <UserPlus size={15} />
              )
            }
          >
            Add
          </Button>
        </form>
      </Card>

      {/* ---------------- the record ---------------- */}
      <Card padded={false}>
        <div className="border-b border-cream-200 px-6 py-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-ink-900">Activity record</h3>
              <p className="text-xs text-ink-500">
                Append-only. This is what makes a shortlist explainable months later.
              </p>
            </div>
            {/* The table used to show the newest 200 lines and say nothing
                about it, so a log of thousands looked complete. Naming the
                total is the difference between a page of a record and a
                record. */}
            {audit !== null && auditTotal !== null && (
              <div className="flex items-center gap-3">
                <p className="tnum text-xs text-ink-500">
                  {auditTotal > audit.length
                    ? `Showing the latest ${audit.length} of ${auditTotal}`
                    : `All ${auditTotal} entries`}
                </p>
                {auditTotal > audit.length && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setAuditLimit((n) => n + AUDIT_PAGE)}
                  >
                    Show more
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>

        {audit === null ? (
          <Loading />
        ) : audit.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-ink-400">
            Nothing recorded yet.
          </p>
        ) : (
          <div className="max-h-[460px] overflow-y-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="sticky top-0 bg-white">
                <tr className="border-b border-cream-200 text-left text-xs uppercase tracking-wider text-ink-400">
                  <th className="px-6 py-2.5 font-semibold">When</th>
                  <th className="px-6 py-2.5 font-semibold">Who</th>
                  <th className="px-6 py-2.5 font-semibold">What</th>
                  <th className="px-6 py-2.5 font-semibold">Ranking</th>
                  <th className="px-6 py-2.5 font-semibold">Detail</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((e, i) => (
                  <tr key={i} className="border-b border-ink-50 last:border-0">
                    <td className="whitespace-nowrap px-6 py-2.5 font-mono text-xs text-ink-500">
                      {whenTextExact(e.at)}
                    </td>
                    <td className="px-6 py-2.5 text-ink-700">{e.actor}</td>
                    <td className="px-6 py-2.5 font-semibold text-ink-900">{label(e.action)}</td>
                    {/* The run id was fetched all along and never shown, so a
                        "Deleted a ranking" line named no ranking. That is the
                        one row in this table that most needs to say which. */}
                    <td className="whitespace-nowrap px-6 py-2.5 font-mono text-xs text-ink-500">
                      {e.run_id || "—"}
                    </td>
                    <td className="px-6 py-2.5 text-ink-500">{e.detail || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};

const Loading: React.FC = () => (
  <div className="flex items-center justify-center py-10">
    <Loader2 size={18} className="animate-spin text-honda-red" />
  </div>
);

export default Admin;
