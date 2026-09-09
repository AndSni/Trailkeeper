// Thin client for the Trailkeeper JSON API. The console authenticates with
// its own JWT pair (access in memory + localStorage, refresh in localStorage)
// and retries a 401 once after refreshing.

const ACCESS_KEY = "tk_console_access";
const REFRESH_KEY = "tk_console_refresh";

let accessToken: string | null = localStorage.getItem(ACCESS_KEY);

export function isSignedIn(): boolean {
  return !!localStorage.getItem(REFRESH_KEY);
}

function store(access: string, refresh: string) {
  accessToken = access;
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function signOut() {
  accessToken = null;
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export async function login(email: string, password: string): Promise<void> {
  const res = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Invalid email or password");
  const body = await res.json();
  store(body.access_token, body.refresh_token);
}

async function refresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return false;
  const res = await fetch("/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) {
    signOut();
    return false;
  }
  const body = await res.json();
  store(body.access_token, body.refresh_token);
  return true;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const send = () =>
    fetch(path, {
      ...init,
      headers: {
        ...(init.headers ?? {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
    });

  let res = await send();
  if (res.status === 401 && (await refresh())) res = await send();
  if (res.status === 401) {
    signOut();
    location.reload();
    throw new Error("Session expired");
  }
  if (!res.ok) throw new Error(`${init.method ?? "GET"} ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

// --- typed endpoints -------------------------------------------------------

export interface Project {
  id: string;
  name: string;
  status: string;
  activity: string;
}

export interface GeoJson {
  type: string;
  coordinates: unknown;
}

export interface Trail {
  id: string;
  name: string;
  status: string;
  length_m: number;
  geometry: GeoJson | null;
}

export interface Task {
  id: string;
  title: string;
  status: string;
  priority: string;
  geometry: GeoJson | null;
}

export interface Structure {
  id: string;
  name: string;
  structure_type: string;
  status: string;
  geometry: GeoJson | null;
}

export interface Snapshot {
  project: Project;
  trails: Trail[];
  tasks: Task[];
  structures: Structure[];
  high_seq: number;
}

export const listProjects = () => api<Project[]>("/projects");
export const getSnapshot = (projectId: string) =>
  api<Snapshot>(`/sync/snapshot?project=${encodeURIComponent(projectId)}`);
