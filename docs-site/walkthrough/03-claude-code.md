# 3. Hand off to Claude Code

This is the moment the workspace earns its keep. Because both repos sit
under a single directory, an agent that can read the filesystem has the
full cross-repo picture in one shot — no manual context-stitching, no
re-explaining the architecture.

## Start a session pointed at the workspace

```bash
cd task-1234-add-export
claude
```

When Claude Code starts here, its working directory is the *workspace
root* — `backend/` and `frontend/` are its visible children. It can
read either, edit either, and reason across both without you switching
contexts.

## A representative prompt

You'd describe the task in the workspace's terms, not in single-repo
terms:

> *Add a CSV export endpoint to the backend at `/api/v1/users/export`
> (returns all users as `text/csv`). On the frontend, add a "Download
> CSV" button to the users page that hits the new endpoint. Keep the
> URL constant in one place on the frontend; use the existing
> `api-client` pattern.*

## What you'd see

The agent searches both repos to find the existing API-route pattern,
the existing client wiring, and the users page. It produces edits in
both:

=== "Backend diff"

    ```diff title="backend/src/acme_backend/routes/users.py"
     from fastapi import APIRouter, Depends
     from sqlalchemy.orm import Session
    +from fastapi.responses import StreamingResponse
    +import csv, io

     router = APIRouter(prefix="/api/v1/users")

     @router.get("")
     def list_users(db: Session = Depends(get_db)):
         return db.query(User).all()
    +
    +
    +@router.get("/export", response_class=StreamingResponse)
    +def export_users(db: Session = Depends(get_db)) -> StreamingResponse:
    +    buf = io.StringIO()
    +    writer = csv.writer(buf)
    +    writer.writerow(["id", "email", "created_at"])
    +    for u in db.query(User).order_by(User.id):
    +        writer.writerow([u.id, u.email, u.created_at.isoformat()])
    +    buf.seek(0)
    +    return StreamingResponse(
    +        iter([buf.getvalue()]),
    +        media_type="text/csv",
    +        headers={"Content-Disposition": 'attachment; filename="users.csv"'},
    +    )
    ```

=== "Frontend diff"

    ```diff title="frontend/src/api/endpoints.ts"
     export const endpoints = {
       users: {
         list: "/api/v1/users",
    +    export: "/api/v1/users/export",
       },
     } as const;
    ```

    ```diff title="frontend/src/pages/users/UsersPage.tsx"
     import { useUsers } from "@/hooks/useUsers";
    +import { endpoints } from "@/api/endpoints";
    +import { Button } from "@/components/ui/Button";

     export function UsersPage() {
       const { users } = useUsers();
       return (
         <div>
    -      <h1>Users</h1>
    +      <div className="flex items-center justify-between">
    +        <h1>Users</h1>
    +        <Button asChild>
    +          <a href={endpoints.users.export} download>
    +            Download CSV
    +          </a>
    +        </Button>
    +      </div>
           <UsersTable rows={users} />
         </div>
       );
     }
    ```

## Why this works

- Both repos are *real worktrees of their canonical clones*, so any
  `git` operation Claude Code runs is git operating in the right place.
  No tooling lies about the underlying state.
- The agent never needs to "remember" which repo's `main` it should
  compare against — the manifest declares the bases, and every repo's
  branch was created from `main` by `brunch init`.
- Tearing the workspace down later doesn't lose the work: branches stay
  in the canonical clones; only the worktrees go away.

!!! brunch-tip "Permissioning the agent"
    For autonomous loops (e.g. `claude --dangerously-skip-permissions` —
    don't, please), or for scoped permission grants, the workspace root
    is a natural sandbox boundary: the agent's working directory and
    everything it touches is *inside* the workspace dir until commit
    time.

## A short cast

The cast below shows the session opening with the workspace dir in
context. The agent edits themselves aren't recorded — Claude Code is
interactive and slow to demo cleanly — but the *setup* is.

<div class="brunch-cast" data-cast="../../assets/casts/03-claude-code.cast"></div>

Next: **[4. Verify →](04-verify.md)**
