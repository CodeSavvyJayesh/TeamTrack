# TeamTrack

Internal team management and work tracking system.
Django 5 - Bootstrap 5 - SQLite (development) / PostgreSQL (production).

One administrator manages a team of members. Each member has their own login,
dashboard, tasks, working hours, files and daily reports. Nothing in the code
knows any member's name: everything is driven by the database.

- Architecture and schema: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Deployment: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- Ether integration contract: [`integrations/ether/README.md`](integrations/ether/README.md)

## Getting started

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser        # this is the administrator account
python manage.py runserver
```

Open http://127.0.0.1:8000/ and sign in with the email and password you just
created. `createsuperuser` asks for an email, not a username - email is the
login identifier throughout this project.

`.env` already exists with a generated `SECRET_KEY`. It is git-ignored;
`.env.example` documents every setting.

## The two rules that shape everything

1. **Members never enter or edit their own working hours.** The administrator
   enters them; members get a read-only view. This is enforced by
   `AdminRequiredMixin` *and* `AdminOnlyWriteMixin` on every write view, and
   covered by tests in `hours/tests.py`.
2. **Members are not assumed to do the same work.** Tasks, hours, files and
   reports are generic. Google Forms tracking is an optional module switched on
   per member by `MemberProfile.tracks_google_forms`.

## First run, in order

1. `createsuperuser` - your administrator account.
2. **Members - Add member** - enter a name and email. An invitation is created
   and emailed. In development the email prints in the terminal running
   `runserver`; copy the link from there.
3. Open the link, set a password, and that account is live.
4. **Tasks - New task** to assign work. **Working Hours - Add hours** to record
   time. Members see both immediately on their own dashboard.

## Apps

| App | Owns |
|---|---|
| `core` | `TimeStampedModel`, permission mixins, `ActivityLog`, `log_activity()`, template filters |
| `accounts` | `User` (email login), `MemberProfile`, `Invitation`, sign in/out, invite acceptance |
| `members` | Administrator-facing member list, detail, edit, activate/deactivate, invitations |
| `work` | `Project`, `Task` |
| `hours` | `WorkSession` and the read-side aggregation helpers |
| `storage` | `UploadedFile` and the permission-checked download view |
| `reports` | `DailyReport` |
| `dashboard` | Member dashboard, admin team overview, activity log |
| `integrations.google` | `TrackedForm`, `FormSubmissionStat`, sync architecture |
| `integrations.ether` | Integration contract and null client. No invented API. |

## Permissions in one table

| | Administrator | Member |
|---|---|---|
| Admin dashboard, member management | yes | 403 |
| See another member's task, hours, report | yes | 404 |
| Create / edit / delete working hours | yes | **403** |
| View working hours | everyone's | own, read-only |
| Create or assign a task | yes | no |
| Change a task's status | any task | own tasks only |
| Upload a file | yes | yes |
| Download a file | any | own, plus anything marked Team |
| Write a daily report | own | own |
| Read daily reports | everyone's | own |

Members get **404**, not 403, on another member's records: a 403 would confirm
the record exists. Querysets are filtered, so there is nothing to leak.

## Deployment

Railway + PostgreSQL + Cloudflare R2. Full runbook:
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

`railway.json` defines the build and start commands. The nightly attendance
cleanup runs free on GitHub Actions, not on the host, because both Railway and
Render charge for scheduled jobs. `render.yaml` is kept as an alternative.

Two things that are easy to get wrong and expensive to discover late:

- **Uploaded files must go to object storage.** Railway wipes the container
  disk on every deploy. Set the `AWS_*` variables or files disappear.
- **`CSRF_TRUSTED_ORIGINS` must list every hostname you serve**, with the
  `https://` prefix, or every form submission fails while every page still loads.

## Tests

```bash
python manage.py test
```

91 tests covering authentication, the invitation lifecycle, every permission
boundary above, duration calculation, upload validation, file visibility, and
the two integration contracts.

## Integrations

Both are dormant and the application runs normally without them.

- **Google Forms** - `sync_form_stats()` writes `FormSubmissionStat` rows.
  Until credentials exist, an administrator types the same rows in by hand and
  every dashboard reads them identically. Implementing the real sync changes
  one file, `integrations/google/client.py`.
- **Ether** - `EtherClient` defines what TeamTrack wants to say; `NullEtherClient`
  does nothing and says so. No endpoints, URLs or payload schemas have been
  invented. See that package's README for the events already being emitted.
