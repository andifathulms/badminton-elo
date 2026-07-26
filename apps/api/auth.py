"""Session auth for the in-app admin (the React "Studio").

The public read API stays open (AllowAny, no auth classes). Only the Studio
write endpoints require a logged-in staff user. Because the SPA is served
same-origin by Django, plain Django session cookies + CSRF are the simplest
secure fit — no tokens to store in JS.

Flow:
  1. Frontend calls GET /api/auth/me on load. @ensure_csrf_cookie plants the
     `csrftoken` cookie so subsequent writes can echo it in X-CSRFToken.
  2. POST /api/auth/login {username, password} authenticates and opens a session.
  3. Writes (studio.py) use SessionAuthentication + IsAdminUser; DRF enforces
     CSRF on those unsafe requests.
"""
from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def _me(user) -> dict:
    """The identity payload the frontend keys its admin gate on."""
    if not user or not user.is_authenticated:
        return {"authenticated": False, "username": None, "is_staff": False}
    return {
        "authenticated": True,
        "username": user.get_username(),
        # Only staff may write. A plain authenticated non-staff user is treated
        # as a viewer (the whole public site is already viewable anyway).
        "is_staff": bool(user.is_staff),
    }


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def me(request):
    """GET /api/auth/me — who am I, and plant the CSRF cookie for later writes."""
    get_token(request)  # forces Set-Cookie: csrftoken so writes can echo it
    return Response(_me(request.user))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def login(request):
    """POST /api/auth/login {username, password} — open a session."""
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""
    if not username or not password:
        return Response(
            {"detail": "username and password required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response(
            {"detail": "Invalid username or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    if not user.is_staff:
        return Response(
            {"detail": "This account is not an administrator."},
            status=status.HTTP_403_FORBIDDEN,
        )
    django_login(request, user)
    return Response(_me(user))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def logout(request):
    """POST /api/auth/logout — end the session."""
    django_logout(request)
    return Response({"authenticated": False, "username": None, "is_staff": False})
