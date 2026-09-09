# TeamTrack - one-command setup for a fresh clone.
#
# Run it from the project folder in PowerShell:
#
#     powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# It creates the virtual environment, installs everything, writes a .env with a
# freshly generated secret key, sets up the database, and creates the
# administrator account. Safe to run twice - it skips whatever already exists.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Step($text) { Write-Host "`n=== $text" -ForegroundColor Cyan }

Step "1/5  Virtual environment"
if (Test-Path ".venv") {
    Write-Host "     already exists, skipping"
} else {
    python -m venv .venv
    Write-Host "     created"
}
& ".\.venv\Scripts\Activate.ps1"

Step "2/5  Dependencies"
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
Write-Host "     installed"

Step "3/5  Configuration (.env)"
if (Test-Path ".env") {
    Write-Host "     already exists, leaving it alone"
} else {
    # A fresh secret key for this machine. Never reuse one between installs.
    # Letters and digits only. Punctuation would be mangled by PowerShell's
    # variable expansion inside a double-quoted argument, and 62^50 is plenty.
    $secret = python -c 'import secrets, string; print("".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(50)))'

    Write-Host ""
    Write-Host "     Email is optional. Leave both blank and invitation links" -ForegroundColor Yellow
    Write-Host "     print in this terminal instead of being sent." -ForegroundColor Yellow
    Write-Host ""
    $mailUser = Read-Host "     Gmail address to send from (or press Enter to skip)"
    $mailPass = ""
    if ($mailUser -ne "") {
        $mailPass = Read-Host "     16-character Gmail App Password (no spaces)"
        $mailPass = $mailPass -replace '\s', ''
    }

    $host_ = if ($mailUser -ne "") { "smtp.gmail.com" } else { "" }
    $from  = if ($mailUser -ne "") { "TeamTrack <$mailUser>" } else { "TeamTrack <noreply@localhost>" }

    @"
SECRET_KEY=$secret
DEBUG=True
ALLOWED_HOSTS=
TIME_ZONE=Asia/Kolkata

INVITATION_EXPIRY_DAYS=7
MAX_UPLOAD_SIZE_MB=10
ATTENDANCE_MAX_HOURS=9

GOOGLE_SERVICE_ACCOUNT_FILE=
ETHER_BASE_URL=
ETHER_API_KEY=

EMAIL_HOST=$host_
EMAIL_PORT=587
EMAIL_HOST_USER=$mailUser
EMAIL_HOST_PASSWORD=$mailPass
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=$from
"@ | Set-Content -Path ".env" -Encoding ascii
    # ascii, NOT utf8: Windows PowerShell 5.1 writes a byte-order mark with
    # -Encoding UTF8, and those three invisible bytes at the start of the file
    # turn the first key into "<BOM>SECRET_KEY". Django then cannot find
    # SECRET_KEY and refuses to start, with an error that points nowhere near
    # the real cause. Everything written here is ASCII, so nothing is lost.

    Write-Host "     written, with a newly generated secret key"
}

Step "4/5  Database"
python manage.py migrate
Write-Host "     ready"

Step "5/5  Administrator account"
# -join guards against python emitting more than one line: .Trim() on an
# array throws, and the script would die at the last step.
$count = (python -c "import os,django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.development'); django.setup(); from accounts.models import User; print(User.objects.filter(role='ADMIN').count())") -join ""
if ($count.Trim() -eq "0") {
    Write-Host "     None yet. Create one now - it asks for an EMAIL, not a username." -ForegroundColor Yellow
    Write-Host ""
    python manage.py createsuperuser
} else {
    Write-Host "     already exists, skipping"
}

Write-Host ""
Write-Host "Done. Start the server with:" -ForegroundColor Green
Write-Host "    .\.venv\Scripts\activate"
Write-Host "    python manage.py runserver 0.0.0.0:8000"
Write-Host ""
Write-Host "Then open  http://127.0.0.1:8000/" -ForegroundColor Green
Write-Host ""
Write-Host "Run 'ipconfig' for the Wi-Fi IPv4 address if other devices need to reach it."
