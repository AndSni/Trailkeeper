import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  createProject,
  createStructure,
  createTask,
  createTrail,
  deleteStructure,
  deleteTask,
  deleteTrail,
  getSnapshot,
  isSignedIn,
  listProjects,
  signOut,
  updateStructure,
  updateTask,
  updateTrail,
  type Project,
  type Snapshot,
} from "./api";
import { Login } from "./Login";
import { MapView, type FocusTarget } from "./MapView";
import { boundsOf, centerOf } from "./geo";

type Tab = "tasks" | "trails" | "structures";
type Mode =
  | { kind: "idle" }
  | { kind: "add-task" }
  | { kind: "add-structure" }
  | { kind: "draw-trail" }
  | { kind: "move"; tab: Tab; id: string }
  | { kind: "form-task"; lon: number; lat: number }
  | { kind: "form-structure"; lon: number; lat: number }
  | { kind: "form-trail" }
  | { kind: "form-project" };

const PRIORITIES = ["low", "medium", "high", "urgent"];
const TASK_STATUSES = ["open", "in_progress", "done", "wontfix"];
const TRAIL_STATUSES = ["open", "closed", "needs_work"];
const DIFFICULTIES = ["", "easy", "moderate", "hard", "expert"];
const STRUCTURE_TYPES = [
  "culvert", "bridge", "boardwalk", "ford", "steps", "retaining_wall",
  "drain", "waterbar", "sign", "gate", "bench", "kiosk", "other",
];
const STRUCTURE_STATUSES = ["good", "monitor", "needs_repair", "failed", "decommissioned"];

export function App() {
  const [authed, setAuthed] = useState(isSignedIn());
  if (!authed) return <Login onDone={() => setAuthed(true)} />;
  return <Console onSignOut={() => setAuthed(false)} />;
}

function Console({ onSignOut }: { onSignOut: () => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [tab, setTab] = useState<Tab>("tasks");
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>({ kind: "idle" });
  const [focus, setFocus] = useState<FocusTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<[number, number][]>([]);

  const setErr = (e: unknown) => setError(e instanceof Error ? e.message : String(e));

  const loadProjects = useCallback(async (selectId?: string) => {
    try {
      const ps = await listProjects();
      const list = Array.isArray(ps) ? ps : [];
      setProjects(list);
      setProjectId((cur) => selectId ?? cur ?? list[0]?.id ?? null);
    } catch (e) {
      setErr(e);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const reload = useCallback(() => {
    if (!projectId) {
      setSnapshot(null);
      return;
    }
    return getSnapshot(projectId).then(setSnapshot).catch(setErr);
  }, [projectId]);

  useEffect(() => {
    setSnapshot(null);
    setSelected(null);
    setMode({ kind: "idle" });
    reload();
  }, [reload]);

  const rows = useMemo(() => {
    if (!snapshot) return [];
    if (tab === "trails")
      return snapshot.trails.map((t) => ({
        id: t.id,
        name: t.name,
        meta: `${t.status} · ${(t.length_m / 1000).toFixed(1)} km`,
        geometry: t.geometry,
      }));
    if (tab === "structures")
      return snapshot.structures.map((s) => ({
        id: s.id,
        name: s.name,
        meta: `${s.structure_type.replace(/_/g, " ")} · ${s.status.replace(/_/g, " ")}`,
        geometry: s.geometry,
      }));
    return snapshot.tasks.map((t) => ({
      id: t.id,
      name: t.title,
      meta: `${t.priority} · ${t.status.replace(/_/g, " ")}`,
      geometry: t.geometry,
    }));
  }, [snapshot, tab]);

  const selectedRow = rows.find((r) => r.id === selected) ?? null;

  function focusGeom(geometry: (typeof rows)[number]["geometry"]) {
    if (!geometry) return;
    const isPoint = geometry.type === "Point";
    setFocus({
      nonce: Date.now(),
      ...(isPoint
        ? { center: centerOf(geometry) ?? undefined }
        : { bounds: boundsOf([geometry]) ?? undefined }),
    });
  }

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await reload();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  function onPick([lon, lat]: [number, number]) {
    if (mode.kind === "add-task") setMode({ kind: "form-task", lon, lat });
    else if (mode.kind === "add-structure") setMode({ kind: "form-structure", lon, lat });
    else if (mode.kind === "draw-trail") setDraft((p) => [...p, [lon, lat]]);
    else if (mode.kind === "move") {
      const { tab: mt, id } = mode;
      setMode({ kind: "idle" });
      run(() =>
        mt === "tasks"
          ? updateTask(id, { lat, lon })
          : mt === "structures"
            ? updateStructure(id, { lat, lon })
            : Promise.resolve(),
      );
    }
  }

  const drawing = mode.kind === "draw-trail";
  const picking =
    mode.kind === "add-task" ||
    mode.kind === "add-structure" ||
    mode.kind === "move" ||
    drawing;

  function cancelDraw() {
    setMode({ kind: "idle" });
    setDraft([]);
  }

  return (
    <div className="app">
      <div className="topbar">
        <span className="brand">Trailkeeper</span>
        <select
          value={projectId ?? ""}
          disabled={projects.length === 0}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.length === 0 && <option value="">No projects</option>}
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <button className="ghost" disabled={busy} onClick={() => setMode({ kind: "form-project" })}>
          ＋ Project
        </button>
        <button
          className="ghost"
          disabled={busy || !projectId}
          title={projectId ? "" : "Select or create a project first"}
          onClick={() => setMode({ kind: "add-task" })}
        >
          ＋ Task
        </button>
        <button className="ghost" disabled={busy} onClick={() => setMode({ kind: "add-structure" })}>
          ＋ Structure
        </button>
        <button
          className="ghost"
          disabled={busy}
          onClick={() => { setDraft([]); setMode({ kind: "draw-trail" }); }}
        >
          ＋ Trail
        </button>
        <span className="spacer" />
        <a href="/app">Dashboard</a>
        <button className="ghost" onClick={() => { signOut(); onSignOut(); }}>Sign out</button>
      </div>

      {drawing ? (
        <div className="banner">
          Click the map to add trail points — {draft.length}{" "}
          {draft.length === 1 ? "point" : "points"}
          <button className="ghost" disabled={!draft.length} onClick={() => setDraft((p) => p.slice(0, -1))}>
            Undo last
          </button>
          <button disabled={draft.length < 2} onClick={() => setMode({ kind: "form-trail" })}>
            Finish
          </button>
          <button className="ghost" onClick={cancelDraw}>Cancel</button>
        </div>
      ) : picking ? (
        <div className="banner">
          {mode.kind === "move" ? "Click the map to set the new location" : "Click the map to place it"}
          <button className="ghost" onClick={() => setMode({ kind: "idle" })}>Cancel</button>
        </div>
      ) : null}
      {error && <div className="err" style={{ margin: 8 }}>{String(error)}</div>}

      <div className="body">
        <div className="panel">
          <div className="tabs">
            {(["tasks", "trails", "structures"] as Tab[]).map((t) => (
              <button
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => { setTab(t); setSelected(null); }}
              >
                {t[0].toUpperCase() + t.slice(1)}
                {snapshot ? ` (${snapshot[t].length})` : ""}
              </button>
            ))}
          </div>

          {projects.length === 0 ? (
            <div className="empty">
              No projects yet. Use <strong>＋ Project</strong> to create the first one.
            </div>
          ) : !projectId ? (
            <div className="empty">Pick a project above.</div>
          ) : selectedRow ? (
            <Detail
              tab={tab}
              row={selectedRow}
              snapshot={snapshot!}
              busy={busy}
              onBack={() => setSelected(null)}
              onFocus={() => focusGeom(selectedRow.geometry)}
              onPatch={(body) =>
                run(() =>
                  tab === "tasks"
                    ? updateTask(selectedRow.id, body)
                    : tab === "structures"
                      ? updateStructure(selectedRow.id, body)
                      : updateTrail(selectedRow.id, body),
                )
              }
              onMove={() => setMode({ kind: "move", tab, id: selectedRow.id })}
              onDelete={() =>
                run(async () => {
                  if (tab === "tasks") await deleteTask(selectedRow.id);
                  else if (tab === "structures") await deleteStructure(selectedRow.id);
                  else await deleteTrail(selectedRow.id);
                  setSelected(null);
                })
              }
            />
          ) : !snapshot ? (
            <div className="empty">Loading…</div>
          ) : rows.length === 0 ? (
            <div className="empty">Nothing here yet.</div>
          ) : (
            <div className="list">
              {rows.map((r) => (
                <div
                  key={r.id}
                  className="row"
                  onClick={() => {
                    if (drawing) return;
                    setSelected(r.id);
                    focusGeom(r.geometry);
                  }}
                >
                  <div className="name">{r.name}</div>
                  <div className="meta">
                    {r.meta}
                    {!r.geometry && <span className="pill" style={{ marginLeft: 6 }}>no location</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <MapView
          snapshot={snapshot}
          focus={focus}
          picking={picking}
          draft={mode.kind === "draw-trail" || mode.kind === "form-trail" ? draft : null}
          onPick={onPick}
        />
      </div>

      {mode.kind === "form-project" && (
        <CreateNameForm
          title="New project"
          label="Project name"
          busy={busy}
          onCancel={() => setMode({ kind: "idle" })}
          onCreate={(name) =>
            run(async () => {
              const p = await createProject(name);
              setMode({ kind: "idle" });
              await loadProjects(p.id);
            })
          }
        />
      )}
      {mode.kind === "form-task" && projectId && (
        <CreateTaskForm
          busy={busy}
          onCancel={() => setMode({ kind: "idle" })}
          onCreate={(title, priority) =>
            run(async () => {
              await createTask(projectId, { title, priority, lat: mode.lat, lon: mode.lon });
              setMode({ kind: "idle" });
              setTab("tasks");
            })
          }
        />
      )}
      {mode.kind === "form-structure" && (
        <CreateStructureForm
          busy={busy}
          onCancel={() => setMode({ kind: "idle" })}
          onCreate={(name, structure_type) =>
            run(async () => {
              await createStructure({ name, structure_type, lat: mode.lat, lon: mode.lon });
              setMode({ kind: "idle" });
              setTab("structures");
            })
          }
        />
      )}
      {mode.kind === "form-trail" && (
        <CreateTrailForm
          points={draft.length}
          busy={busy}
          onCancel={cancelDraw}
          onCreate={(name, difficulty, status) =>
            run(async () => {
              await createTrail({
                name,
                difficulty: difficulty || undefined,
                status,
                points: draft.map(([lng, lat]) => [lat, lng]),
              });
              setDraft([]);
              setMode({ kind: "idle" });
              setTab("trails");
            })
          }
        />
      )}
    </div>
  );
}

function CreateTrailForm({
  points,
  busy,
  onCancel,
  onCreate,
}: {
  points: number;
  busy: boolean;
  onCancel: () => void;
  onCreate: (name: string, difficulty: string, status: string) => void;
}) {
  const [name, setName] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [status, setStatus] = useState("open");
  return (
    <Modal title={`New trail · ${points} points`} onCancel={onCancel}>
      <label>Name</label>
      <input value={name} autoFocus onChange={(e) => setName(e.target.value)} />
      <label>Difficulty</label>
      <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
        {DIFFICULTIES.map((d) => (
          <option key={d} value={d}>{d || "(none)"}</option>
        ))}
      </select>
      <label>Status</label>
      <select value={status} onChange={(e) => setStatus(e.target.value)}>
        {TRAIL_STATUSES.map((s) => (
          <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
        ))}
      </select>
      <div className="detail-actions">
        <button disabled={busy || !name.trim()} onClick={() => onCreate(name.trim(), difficulty, status)}>
          Create trail
        </button>
        <button className="ghost" onClick={onCancel}>Cancel</button>
      </div>
    </Modal>
  );
}

function Detail({
  tab,
  row,
  snapshot,
  busy,
  onBack,
  onFocus,
  onPatch,
  onMove,
  onDelete,
}: {
  tab: Tab;
  row: { id: string; name: string };
  snapshot: Snapshot;
  busy: boolean;
  onBack: () => void;
  onFocus: () => void;
  onPatch: (body: Record<string, string>) => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  const task = tab === "tasks" ? snapshot.tasks.find((t) => t.id === row.id) : null;
  const structure = tab === "structures" ? snapshot.structures.find((s) => s.id === row.id) : null;
  const trail = tab === "trails" ? snapshot.trails.find((t) => t.id === row.id) : null;
  const status = task?.status ?? structure?.status ?? trail?.status ?? "";
  const statuses =
    tab === "tasks" ? TASK_STATUSES : tab === "structures" ? STRUCTURE_STATUSES : TRAIL_STATUSES;

  return (
    <div className="detail">
      <button className="ghost" onClick={onBack}>← Back</button>
      <h3>{row.name}</h3>

      <label>Status</label>
      <select value={status} disabled={busy} onChange={(e) => onPatch({ status: e.target.value })}>
        {statuses.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
      </select>

      {task && (
        <>
          <label>Priority</label>
          <select
            value={task.priority}
            disabled={busy}
            onChange={(e) => onPatch({ priority: e.target.value })}
          >
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </>
      )}
      {structure && (
        <>
          <label>Type</label>
          <select
            value={structure.structure_type}
            disabled={busy}
            onChange={(e) => onPatch({ structure_type: e.target.value })}
          >
            {STRUCTURE_TYPES.map((t) => (
              <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
            ))}
          </select>
        </>
      )}

      <div className="detail-actions">
        <button className="ghost" onClick={onFocus}>Zoom to</button>
        {tab !== "trails" && (
          <button className="ghost" disabled={busy} onClick={onMove}>Move</button>
        )}
        <button className="danger" disabled={busy} onClick={onDelete}>Delete</button>
      </div>
    </div>
  );
}

function CreateTaskForm({
  busy,
  onCancel,
  onCreate,
}: {
  busy: boolean;
  onCancel: () => void;
  onCreate: (title: string, priority: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("medium");
  return (
    <Modal title="New task" onCancel={onCancel}>
      <label>Title</label>
      <input value={title} autoFocus onChange={(e) => setTitle(e.target.value)} />
      <label>Priority</label>
      <select value={priority} onChange={(e) => setPriority(e.target.value)}>
        {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <div className="detail-actions">
        <button disabled={busy || !title.trim()} onClick={() => onCreate(title.trim(), priority)}>
          Create
        </button>
        <button className="ghost" onClick={onCancel}>Cancel</button>
      </div>
    </Modal>
  );
}

function CreateStructureForm({
  busy,
  onCancel,
  onCreate,
}: {
  busy: boolean;
  onCancel: () => void;
  onCreate: (name: string, type: string) => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState("culvert");
  return (
    <Modal title="New structure" onCancel={onCancel}>
      <label>Name</label>
      <input value={name} autoFocus onChange={(e) => setName(e.target.value)} />
      <label>Type</label>
      <select value={type} onChange={(e) => setType(e.target.value)}>
        {STRUCTURE_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
      </select>
      <div className="detail-actions">
        <button disabled={busy || !name.trim()} onClick={() => onCreate(name.trim(), type)}>
          Create
        </button>
        <button className="ghost" onClick={onCancel}>Cancel</button>
      </div>
    </Modal>
  );
}

function CreateNameForm({
  title,
  label,
  busy,
  onCancel,
  onCreate,
}: {
  title: string;
  label: string;
  busy: boolean;
  onCancel: () => void;
  onCreate: (name: string) => void;
}) {
  const [name, setName] = useState("");
  return (
    <Modal title={title} onCancel={onCancel}>
      <label>{label}</label>
      <input value={name} autoFocus onChange={(e) => setName(e.target.value)} />
      <div className="detail-actions">
        <button disabled={busy || !name.trim()} onClick={() => onCreate(name.trim())}>Create</button>
        <button className="ghost" onClick={onCancel}>Cancel</button>
      </div>
    </Modal>
  );
}

function Modal({
  title,
  onCancel,
  children,
}: {
  title: string;
  onCancel: () => void;
  children: ReactNode;
}) {
  return (
    <div className="modal-scrim" onClick={onCancel}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}
