from __future__ import annotations

from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token


@sync_to_async
def _get_user_from_token(token_key: str):
    if not token_key:
        return AnonymousUser()
    try:
        return Token.objects.select_related("user").get(key=token_key).user
    except Token.DoesNotExist:
        return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        query = parse_qs(query_string)
        token_key = ""
        token_values = query.get("token") or []
        if token_values:
            token_key = str(token_values[0]).strip()

        scope["user"] = await _get_user_from_token(token_key)
        return await super().__call__(scope, receive, send)


def TokenAuthMiddlewareStack(inner):
    return TokenAuthMiddleware(inner)
