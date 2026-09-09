import { useEffect, useMemo, useState } from "react";
import {
  getSnapshot,
  isSignedIn,
  listProjects,
  signOut,
  type Project,
  type Snapshot,
} from "./api";
import { Login } from "./Login";
import { MapView, type FocusTarget } from "./MapView";
import { boundsOf, centerOf } from "./geo";

type Tab = "trails" | "tasks" | "structures";

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
  const [focus, setFocus] = useState<FocusTarget | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then((ps) => {
        setProjects(ps);
        if (ps.length) setProjectId((cur) => cur ?? ps[0].id);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    setSnapshot(null);
    getSnapshot(projectId)
      .then(setSnapshot)
      .catch((e) => setError(String(e)));
  }, [projectId]);

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

  function focusRow(geometry: (typeof rows)[number]["geometry"]) {
    if (!geometry) return;
    const b = boundsOf([geometry]);
    const isPoint = geometry.type === "Point";
    setFocus({
      nonce: Date.now(),
      ...(isPoint ? { center: centerOf(geometry) ?? undefined } : { bounds: b ?? undefined }),
    });
  }

  return (
    <div className="app">
      <div className="topbar">
        <span className="brand">Trailkeeper</span>
        <select
          value={projectId ?? ""}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <span className="spacer" />
        <a href="/app">Dashboard</a>
        <button
          className="ghost"
          onClick={() => {
            signOut();
            onSignOut();
          }}
        >
          Sign out
        </button>
      </div>

      {error && <div className="err" style={{ margin: 8 }}>{error}</div>}

      <div className="body">
        <div className="panel">
          <div className="tabs">
            {(["tasks", "trails", "structures"] as Tab[]).map((t) => (
              <button
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => setTab(t)}
              >
                {t[0].toUpperCase() + t.slice(1)}
                {snapshot ? ` (${snapshot[t].length})` : ""}
              </button>
            ))}
          </div>
          <div className="list">
            {!snapshot && <div className="empty">Loading…</div>}
            {snapshot && rows.length === 0 && <div className="empty">Nothing here yet.</div>}
            {rows.map((r) => (
              <div key={r.id} className="row" onClick={() => focusRow(r.geometry)}>
                <div className="name">{r.name}</div>
                <div className="meta">
                  {r.meta}
                  {!r.geometry && <span className="pill" style={{ marginLeft: 6 }}>no location</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
        <MapView snapshot={snapshot} focus={focus} />
      </div>
    </div>
  );
}
