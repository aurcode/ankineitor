import os
import sys
from pathlib import Path

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

project_root = Path(__file__).resolve().parents[3]
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ankineitor_web.settings")

django_asgi_app = get_asgi_application()

from pipeline_api.routing import websocket_urlpatterns
from pipeline_api.ws_auth import TokenAuthMiddlewareStack

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": TokenAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
