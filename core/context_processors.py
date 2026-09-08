"""
Works out which sidebar item to highlight from the request path.

Doing it here rather than passing `nav` from twenty views means adding a page
never requires remembering to set it.
"""

NAV_BY_PREFIX = [
    ("/members", "members"),
    ("/tasks/projects", "projects"),
    ("/tasks", "tasks"),
    ("/hours", "hours"),
    ("/files", "files"),
    ("/reports", "reports"),
    ("/forms", "forms"),
    ("/activity", "activity"),
    ("/accounts/profile", "profile"),
    ("/setup", "settings"),
    ("/notifications", "notifications"),
    ("/attendance", "attendance"),
]


def navigation(request):
    path = request.path
    for prefix, name in NAV_BY_PREFIX:
        if path.startswith(prefix):
            return {"nav": name}
    return {"nav": "dashboard"}
