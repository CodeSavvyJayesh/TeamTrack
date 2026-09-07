# Ether integration

**Status: not implemented, by design.**

Ether is a separate platform. Its API specification is not available to this
project, so nothing in this package contacts a network, and no endpoint, URL,
payload shape or auth scheme has been invented. Guessing at them would produce
code that looks finished and fails the moment the real API appears.

What exists instead is a contract and a no-op implementation of it.

## Files

| File | Purpose |
|---|---|
| `base.py` | `EtherClient` – abstract base class. The operations TeamTrack wants. |
| `null.py` | `NullEtherClient` – the default. Logs the call, does nothing, returns `False`. |
| `config.py` | `get_ether_client()` / `notify_ether()` – the only things callers import. |

## How the rest of the app uses it

```python
from integrations.ether.config import notify_ether

notify_ether("task.completed", {"task_id": task.pk, "member_id": task.assigned_to_id})
```

`notify_ether` never raises. An integration that is not configured, or is down,
must not be able to break a member marking a task complete.

## Events TeamTrack currently emits

These fire today and go nowhere. They are the list you would implement first.

| Event type | When |
|---|---|
| `member.activated` | An invited person sets their password and the account goes live |
| `member.deactivated` | An administrator deactivates a member |
| `task.created` | An administrator creates and assigns a task |
| `task.completed` | A task moves to Completed |
| `hours.recorded` | An administrator saves a work session |
| `report.submitted` | A member files a daily report |

## To implement a real client

1. Write `HttpEtherClient(EtherClient)` in a new `http.py`, implementing
   `send_event` and `fetch_status` against the real specification.
2. Have it read `settings.ETHER_BASE_URL` and `settings.ETHER_API_KEY`.
3. Return it from `get_ether_client()` when `ETHER_BASE_URL` is set.
4. Set `is_live` to `True`.

Nothing outside this package needs to change.

## Inbound webhooks

If Ether needs to call TeamTrack, add `urls.py` here and include it under
`/integrations/ether/` in `config/urls.py`. Keep it inside this package so the
integration stays removable in one piece.
