"""Hand a permission-checked file to nginx (X-Accel-Redirect) instead of streaming it from Python."""
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse


def sendfile(request, filename, **kwargs):
    relative = Path(filename).resolve().relative_to(Path(settings.MEDIA_ROOT).resolve())
    response = HttpResponse()
    response["X-Accel-Redirect"] = settings.SENDFILE_URL + quote(relative.as_posix())
    return response
