"""Server-rendered web console (Phase 6): registration / login / invite
onboarding plus a read-only dashboard. Shares the FastAPI app, the database
and the auth primitives with the JSON API; the browser session is a
refresh-token cookie (`tk_session`).
"""
