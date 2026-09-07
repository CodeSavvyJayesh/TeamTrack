# TeamTrack — Architecture Proposal

Internal Team Management & Work Tracking System
Django 5.x · SQLite (dev) → PostgreSQL (prod) · Bootstrap 5 · Chart.js

**Status: awaiting approval. No application code written yet.**

---

## A. Understanding of the requirements

One admin (you) manages a team of members whose work types differ. Everything the app
stores is per-member and driven by the database, never by hardcoded names.

The non-obvious constraints I am treating as hard rules:

1. **Work hours are admin-entered only.** No clock-in/clock-out for members. Members get a
   read-only view of their own hours. Enforced in the backend, not just by hiding buttons.
2. **Google Forms is a module, not a foundation.** The app must run correctly with zero
   Google credentials configured. Nothing in the core depends on it.
3. **Ether is a contract, not an implementation.** I will define an interface and a
   null/no-op adapter. No invented endpoints, no fake payloads.
4. **Members are heterogeneous.** The core models are generic (task, hour, file, report);
   work-type-specific data lives in optional modules attached to a member.
5. **Deactivate, never delete.** Historical records survive a member leaving.

### Contradictions and gaps I found in the brief

| # | Issue | My resolution |
|---|---|---|
| 1 | §5 says members cannot edit their own working hours; §10 says members "may update their own task status" | Different objects, no real conflict. Hours: read-only for members, always. Task status: members **may** change status on tasks assigned to them, but only between Pending/In Progress/Completed/Blocked. They cannot change title, assignee, priority, due date, or project. |
| 2 | §11 lists "Total duration" as a stored field, but §11 also says it is calculated | Store it as a computed, persisted field (`duration_minutes`) written in `save()`. Persisted so we can aggregate in SQL cheaply; recomputed on every save so it can never drift. |
| 3 | §14 says both admin and members upload files; §14 also says members must not see each other's private files | Needs a visibility rule the brief does not specify. See §G — I propose a three-level `visibility` field (Private / Team / Admin-only) defaulting to **Private**. |
| 4 | §12 daily reports — brief does not say who writes them | Assumption: **members write their own daily reports**, admin reads all and can comment. This is the only reading that makes "different members report different types of work" meaningful. Flag if you meant otherwise. |
| 5 | §8 member dashboard shows "Forms Submitted" | Only rendered for members whose profile has the Google Forms module enabled. Others do not see an empty/zero card. |
| 6 | §4 admin list includes "invite members by email" and §7 requires real email | Dev uses Django's console email backend. Production SMTP config comes from env vars. Nothing blocks local development. |
| 7 | §18 lists `MemberProfile` separate from `User` | Kept. Custom `User` holds auth + role; `MemberProfile` holds work-related attributes. Reasoning in §D. |

---

## B. Proposed architecture

A single Django project, `config`, with eight small apps. Layered, but only two layers —
no repository pattern, no service layer for CRUD.

```
Request
  ↓
URLs (namespaced per app)
  ↓
Views (CBVs, with permission mixins)   ← authorization lives here + in querysets
  ↓
Forms (validation)
  ↓
Models + Managers (business rules: duration calc, visibility querysets)
  ↓
Database
```

Cross-cutting pieces:

- `core/` — abstract base models (`TimeStampedModel`), permission mixins, template tags,
  the `log_activity()` helper. Every other app imports from here; `core` imports from nobody.
- `integrations/` — outward-facing adapters (Google, Ether). Called by views/management
  commands, never the reverse. Business apps do not import `integrations` directly; the
  Google module writes into its own models, and dashboards read those models.

**Why this shape:** each app owns one noun and its views. You can delete `integrations/`
entirely and the app still runs. That is the test for "not over-engineered."

### Settings

```
config/settings/
├── base.py        # everything shared
├── development.py # DEBUG=True, SQLite, console email
└── production.py  # DEBUG=False, PostgreSQL, SMTP, security headers
```

`DJANGO_SETTINGS_MODULE` defaults to `config.settings.development`. Secrets read from `.env`
via `python-decouple` (one small dependency, or `os.environ` + a tiny loader if you'd rather
have zero).

---

## C. Proposed Django apps

| App | Owns | Why it exists separately |
|-----|------|--------------------------|
| `core` | Base models, mixins, `log_activity`, template filters (`duration_format`) | Shared code with no models of its own except `ActivityLog` |
| `accounts` | `User` (custom), `MemberProfile`, `Invitation`, login/logout, invite accept | Auth is its own concern and must be first (custom user model can't be added later) |
| `members` | Admin-facing member list, detail, add, edit, activate/deactivate | Admin views over `accounts` models — separated so `accounts` stays about auth |
| `work` | `Project`, `Task` | Task management |
| `hours` | `WorkSession` | The most permission-sensitive module — worth its own boundary |
| `reports` | `DailyReport` | Daily reporting |
| `storage` | `UploadedFile` + protected download view | Named `storage` not `files` to avoid shadowing stdlib-ish names |
| `dashboard` | Member dashboard, admin dashboard, aggregation queries | Read-only app that composes data from the others |
| `integrations` | `google/`, `ether/` | Adapters only |

Nine directories total (`integrations` has two subpackages, not two apps). No app exists
just to hold one model.

**Note on `accounts` vs `members`:** these could be one app. I split them because
`accounts` must be installed and migrated before anything else (custom user model), and
keeping admin CRUD screens out of it keeps that migration surface small. If you'd rather
have one app, say so now — it's cheap to merge before Phase 2, expensive after.

---

## D. Database schema

### Relationship overview

```
User (1)──(1) MemberProfile
User (1)──(*) Task           [assigned_to]
User (1)──(*) Task           [created_by]
User (1)──(*) WorkSession    [member]
User (1)──(*) WorkSession    [entered_by / updated_by]
User (1)──(*) DailyReport
User (1)──(*) UploadedFile   [uploaded_by]
User (1)──(*) Invitation     [invited_by]
User (1)──(*) ActivityLog    [actor]

Project (1)──(*) Task
Task (*)──(*) DailyReport            [related_tasks, M2M]
Task (1)──(*) UploadedFile           [related_task, nullable]
Project (1)──(*) UploadedFile        [project, nullable]

MemberProfile (1)──(*) TrackedForm   [google module, optional]
TrackedForm (1)──(*) FormSubmissionStat
```

### Models

#### `accounts.User` (extends `AbstractUser`)

| Field | Type | Notes |
|---|---|---|
| `email` | EmailField | **unique, this is the login field** (`USERNAME_FIELD`) |
| `username` | — | removed; email is the identifier |
| `full_name` | CharField(150) | replaces first/last split |
| `role` | CharField(choices: `ADMIN`, `MEMBER`) | authoritative role flag |
| `is_active` | BooleanField | Django's own — used for deactivation |
| `date_joined`, `last_login` | inherited | |

Helper properties: `is_admin_user` (returns `role == ADMIN`). Note: kept distinct from
Django's `is_staff`/`is_superuser`, which stay for Django Admin access only.

> **Why a custom user model now:** Django makes swapping the user model after the first
> migration extremely painful. This is the one piece of up-front design that is non-negotiable.

#### `accounts.MemberProfile` (OneToOne → User)

| Field | Type | Notes |
|---|---|---|
| `user` | OneToOneField(User, CASCADE) | |
| `work_type` | CharField(100) | free text, e.g. "Operations", "Developer", "Research" |
| `department` | CharField(100, blank) | |
| `phone` | CharField(20, blank) | |
| `joined_on` | DateField(null) | |
| `notes` | TextField(blank) | admin-only notes |
| `tracks_google_forms` | BooleanField(default=False) | **the switch that shows/hides the Forms module for this member** |

Created automatically via signal when a User is created.

#### `accounts.Invitation`

| Field | Type | Notes |
|---|---|---|
| `email` | EmailField(unique per pending) | |
| `full_name` | CharField(150) | |
| `work_type`, `department` | CharField | pre-fills profile on acceptance |
| `token` | CharField(64, unique, indexed) | `secrets.token_urlsafe(32)` |
| `invited_by` | FK(User, PROTECT) | |
| `created_at` | DateTimeField(auto) | |
| `expires_at` | DateTimeField | default now + `INVITATION_EXPIRY_DAYS` (env, default 7) |
| `accepted_at` | DateTimeField(null) | null = still pending |

Properties: `is_expired`, `is_valid`. Only the token is stored — never a password.

#### `work.Project`

`name` (unique), `description`, `is_active`, `created_by` FK, `created_at`.
Generic container; a "Project" for Jayesh may be a codebase, for someone else a campaign.

#### `work.Task`

| Field | Type | Notes |
|---|---|---|
| `title` | CharField(200) | |
| `description` | TextField(blank) | |
| `project` | FK(Project, SET_NULL, null) | |
| `assigned_to` | FK(User, PROTECT, related_name='tasks') | |
| `created_by` | FK(User, PROTECT) | |
| `status` | CharField(choices) | `PENDING`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED` |
| `priority` | CharField(choices) | `LOW`, `MEDIUM`, `HIGH`, `URGENT` |
| `due_date` | DateField(null) | |
| `created_at` / `updated_at` | auto | |
| `completed_at` | DateTimeField(null) | set automatically when status → COMPLETED, cleared if moved back |
| `notes` | TextField(blank) | |

Indexes: `(assigned_to, status)`, `(status, due_date)`.

#### `hours.WorkSession`

| Field | Type | Notes |
|---|---|---|
| `member` | FK(User, PROTECT, related_name='work_sessions') | |
| `date` | DateField(indexed) | |
| `start_time` | TimeField | |
| `end_time` | TimeField | |
| `duration_minutes` | PositiveIntegerField | **computed in `save()`, never user-supplied** |
| `note` | CharField(255, blank) | |
| `entered_by` | FK(User, PROTECT, related_name='+') | audit |
| `updated_by` | FK(User, PROTECT, null, related_name='+') | audit |
| `created_at` / `updated_at` | auto | |

Constraints:
- `UniqueConstraint(member, date, start_time)` — prevents duplicate entry
- `CheckConstraint(end_time > start_time)` — no overnight sessions in v1 (see assumption L4)
- `clean()` rejects overlapping sessions for the same member/date

Duration: `(end - start)` in minutes. `10:00 → 16:30` = 390 → displayed `6h 30m` via a
`duration_format` template filter.

#### `reports.DailyReport`

`member` FK, `date`, `summary` TextField, `work_completed` TextField, `blockers`
TextField(blank), `notes` TextField(blank), `related_tasks` M2M(Task, blank),
`created_at`/`updated_at`. `UniqueConstraint(member, date)` — one report per member per day.

#### `storage.UploadedFile`

| Field | Type | Notes |
|---|---|---|
| `file` | FileField(upload_to=`uploads/%Y/%m/<user_id>/`) | |
| `original_name` | CharField(255) | captured on upload |
| `content_type` | CharField(100) | |
| `size_bytes` | PositiveBigIntegerField | |
| `uploaded_by` | FK(User, PROTECT) | |
| `description` | CharField(255, blank) | |
| `related_task` | FK(Task, SET_NULL, null, blank) | |
| `project` | FK(Project, SET_NULL, null, blank) | |
| `visibility` | CharField(choices) | `PRIVATE` (default), `TEAM`, `ADMIN_ONLY` |
| `uploaded_at` | auto | |

#### `core.ActivityLog`

`actor` FK(User, SET_NULL, null), `verb` CharField(choices — a fixed enum, e.g.
`MEMBER_INVITED`, `WORK_HOURS_EDITED`), `target_repr` CharField(255) (a human string, not a
generic FK), `target_model` CharField(50, blank), `target_id` PositiveIntegerField(null),
`created_at` (indexed).

> **Deliberate simplification:** no `GenericForeignKey`. Storing model name + id + a display
> string keeps the log append-only and immune to deletions, and avoids the contenttypes
> query overhead. §20 says do not overcomplicate audit logging in v1.

#### `integrations.google` models (Phase 9)

- `TrackedForm` — `member` FK, `name`, `google_form_id` (blank until configured),
  `sheet_id` (blank), `is_active`
- `FormSubmissionStat` — `form` FK, `date`, `submission_count`, `verified_count`,
  `synced_at`. `UniqueConstraint(form, date)`. Populated by a sync command, or entered
  manually by admin until Google is wired up.

---

## E. Roles and permission matrix

Two roles on `User.role`. Enforcement is layered:
**(1)** view mixin blocks the request, **(2)** queryset scoping means even a guessed URL
returns 404, **(3)** forms omit fields a member may not set.

| Capability | Admin | Member |
|---|---|---|
| Admin dashboard | ✅ | ❌ 403 |
| Own dashboard | ✅ | ✅ |
| View any member's detail page | ✅ | ❌ 404 |
| Add / invite member | ✅ | ❌ |
| Activate / deactivate member | ✅ | ❌ |
| Edit any profile | ✅ | own contact fields only |
| View all tasks | ✅ | own only |
| Create / assign task | ✅ | ❌ |
| Edit task title/assignee/priority/due date | ✅ | ❌ |
| Change task **status** | ✅ any | ✅ own tasks only |
| **Create work hours** | ✅ | ❌ **403** |
| **Edit work hours** | ✅ | ❌ **403** |
| View work hours | ✅ all | ✅ own, read-only |
| Write daily report | ✅ any | ✅ own only |
| Read daily reports | ✅ all | ✅ own only |
| Upload file | ✅ | ✅ |
| Download file | ✅ any | own, or `TEAM` visibility |
| Delete file | ✅ | own only |
| View activity log | ✅ | own entries only |
| Django Admin (`/django-admin/`) | ✅ (superuser) | ❌ |

Implementation:

```python
# core/mixins.py
class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self): return self.request.user.is_admin_user
    raise_exception = True   # 403, not a redirect loop

class OwnerOrAdminMixin(LoginRequiredMixin):
    """Scopes get_queryset() to the requesting user unless they are admin."""
```

The rule I will follow everywhere: **a member's queryset is filtered, not just their
template.** `WorkSessionListView` for a member returns
`WorkSession.objects.filter(member=self.request.user)` — so `/hours/42/` for someone else's
record is a 404, not a 403, and leaks nothing.

---

## F. Authentication and invitation flow

Login is by **email + password**. No public signup — accounts exist only by invitation.

```
Admin → Members → Add Member
   │   (name, email, work type, department)
   ▼
Invitation created  ──►  token = secrets.token_urlsafe(32)
   │                     expires_at = now + 7 days
   ▼
Email sent  ──►  dev: console backend (link printed in terminal)
   │            prod: SMTP from env vars
   ▼
Member opens /invite/accept/<token>/
   │
   ├─ token unknown        → "This invitation link is not valid."
   ├─ already accepted     → "This invitation has already been used." + login link
   ├─ expired              → "This invitation has expired." + ask admin to resend
   ▼
Set-password form (Django's AdminPasswordChangeForm validators + AUTH_PASSWORD_VALIDATORS)
   ▼
Atomic transaction:
   User created (role=MEMBER, is_active=True) + MemberProfile from invitation fields
   Invitation.accepted_at = now
   ActivityLog: MEMBER_ACTIVATED
   ▼
Redirect to login
```

Password reset uses Django's built-in `PasswordResetView` chain — no custom crypto anywhere.
Deactivating a member sets `is_active=False`; Django's `ModelBackend` then refuses login
automatically, and all their historical records stay intact.

---

## G. File upload architecture

**Files are never served by the web server directly.** `MEDIA_URL` is not exposed publicly.
Every download goes through a permission-checked view:

```
GET /files/<pk>/download/
  → view fetches UploadedFile
  → checks: uploaded_by == request.user  OR  user.is_admin_user  OR  visibility == TEAM
  → dev:  FileResponse(open(path,'rb'), as_attachment=True)
  → prod: X-Accel-Redirect / X-Sendfile header (nginx serves the bytes)
```

Files are stored on disk under `MEDIA_ROOT` with a randomised filename; the human-readable
name lives in `original_name` and is set as the `Content-Disposition` filename on download.
Only metadata is in the database.

Validation on upload:
- extension allowlist from settings (default: pdf, doc(x), xls(x), csv, txt, png, jpg, zip)
- max size from env, default 10 MB
- `Content-Disposition: attachment` always, plus `X-Content-Type-Options: nosniff`, so a
  malicious `.html` upload can never execute in your domain's origin

Storage stays swappable: `DEFAULT_FILE_STORAGE` is read from env, so moving to S3 later is a
settings change plus one package, with no model or view rewrite.

---

## H. Google Forms integration strategy

Phase 9 builds the **shape**, not a connection.

```
integrations/google/
├── models.py       TrackedForm, FormSubmissionStat
├── client.py       GoogleSheetsClient — reads creds from env; raises
│                   IntegrationNotConfigured if absent
├── services.py     sync_form_stats(form) — the only function the rest of the app calls
└── management/commands/sync_google_forms.py
```

Contract: **if `GOOGLE_SERVICE_ACCOUNT_FILE` is unset, the app behaves exactly as if the
module did not exist.** Dashboards read `FormSubmissionStat` rows; whether those rows came
from a sync command or from admin manual entry is invisible to them. That means the Forms
cards work from day one with hand-entered numbers, and turning Google on later changes only
where the rows come from.

The `MemberProfile.tracks_google_forms` flag decides whether any Forms UI renders for that
member — so Jayesh never sees a "Forms Submitted: 0" card.

---

## I. Ether integration strategy

I will not invent an API. What Phase 10 delivers:

```
integrations/ether/
├── base.py     EtherClient — abstract base class defining the *intended* operations
│               (send_event, fetch_status). Every method raises NotImplementedError.
├── null.py     NullEtherClient — the default. Logs the call, does nothing, returns None.
├── config.py   get_ether_client() — returns the configured client, NullEtherClient by default
└── README.md   Exactly what specs are needed to implement a real client
```

The core app calls `get_ether_client().send_event(...)` at a handful of well-defined points
(e.g. task completed, member activated). Today those calls are no-ops. When you have the real
Ether spec, you write one `HttpEtherClient(EtherClient)` subclass, point an env var at it, and
touch nothing else. Webhooks, when they arrive, get their own URL module inside this package.

**No fake endpoints, no placeholder URLs, no pretend response schemas.**

---

## J. UI and page structure

Bootstrap 5.3 (local static files, not CDN, so it works offline). One base template:

```
templates/
├── base.html                 <html>, sidebar, topbar, messages framework, blocks
├── partials/
│   ├── _sidebar.html         renders admin or member nav from request.user.role
│   ├── _topbar.html
│   └── _pagination.html
├── registration/             login, password reset, invite accept
└── <app>/                    per-app templates
```

Layout: fixed left sidebar (collapses to offcanvas under 768px) · topbar with user menu ·
content area with a page-title block.

| Member nav | Admin nav |
|---|---|
| Dashboard | Dashboard |
| My Tasks | Members |
| Working Hours | Tasks |
| My Reports | Working Hours |
| Files | Reports |
| Profile | Files |
| *(Google Forms — only if enabled)* | Activity Log |

Charts: exactly three, all Chart.js.
1. Admin dashboard — team hours, last 7 days (bar)
2. Member dashboard — own hours, last 7 days (bar)
3. Member detail — task status breakdown (doughnut)

Data reaches Chart.js via `json_script` in the template, not an API call. No other charts —
§15 says do not overload the dashboard.

---

## K. Development phases

Same order as your brief. Each phase ends with a runnable app, exact commands, and a manual
test you can perform.

| Phase | Deliverable | Runnable at end? |
|---|---|---|
| 1 | Project setup, settings split, base template, git | ✅ blank styled page |
| 2 | Custom user, roles, login/logout, mixins | ✅ login works |
| 3 | Profiles, member CRUD, invitations | ✅ invite + accept works |
| 4 | Projects, tasks, assignment, status | ✅ |
| 5 | Work sessions, admin entry, member read-only | ✅ |
| 6 | File upload + protected download | ✅ |
| 7 | Daily reports, activity log | ✅ |
| 8 | Both dashboards, stats, charts | ✅ |
| 9 | Google Forms models + sync architecture | ✅ (works without credentials) |
| 10 | Ether interface + null client | ✅ |
| 11 | Test suite, security review | ✅ |
| 12 | PostgreSQL, static/media, deployment docs | ✅ |

Phase 2 must land before anything else — the custom user model cannot be introduced later
without destroying migrations.

---

## L. Assumptions I had to make

Flag any of these you disagree with before Phase 1.

1. **Login identifier is email, not username.** The brief only ever mentions email.
2. **Daily reports are written by members**, read by admin (§12 is silent on authorship).
3. **File visibility defaults to Private**, with a Team option the uploader can choose. The
   brief requires members not see each other's private files but never defines the sharing
   model.
4. **No overnight work sessions in v1.** `end_time` must be after `start_time` on the same
   date. If someone works 22:00 → 02:00, that's two records. Tell me if you need overnight
   support and I'll model it as a nullable `end_date` instead.
5. **Members can change status on their own tasks** but nothing else about them (§10 says
   "if appropriate" — this is the narrowest useful reading).
6. **One admin role, not per-object permissions.** Any user with `role=ADMIN` sees
   everything. No team-lead middle tier — the brief describes exactly one administrator.
7. **`python-decouple` for env vars.** One 20 KB dependency. Say the word and I'll use plain
   `os.environ` with a tiny loader instead, for zero extra packages.
8. **Django 5.x on Python 3.11+.** I'll confirm your local Python version in Phase 1.
9. **No DRF until Phase 9 at the earliest**, and only if the Google sync actually needs it.
   Your brief says add it at the correct stage — I don't think Phases 1–8 need it at all.
10. **Timezone `Asia/Kolkata`, `USE_TZ=True`.** Work sessions store naive date + time fields
    deliberately — a shift is "10:00 to 16:30 local", not an instant on a UTC timeline.

---

## Decisions I need from you before Phase 1

1. Approve or amend the schema in §D — particularly `MemberProfile` fields and the
   `visibility` model in §G.
2. Keep `accounts` and `members` as two apps, or merge into one?
3. `python-decouple`, or zero extra dependencies?
4. Any of the ten assumptions in §L wrong?

Once you approve, Phase 1 starts: exact terminal commands, every file, and where each goes.
