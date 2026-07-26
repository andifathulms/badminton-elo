"""Create (or update) the Studio admin login — a non-interactive superuser.

`manage.py createsuperuser` works too, but this is scriptable and idempotent:
re-running just resets the password. Credentials come from flags or, failing
that, the DJANGO_ADMIN_USER / DJANGO_ADMIN_PASSWORD env vars.

    python manage.py create_admin --username admin --password 'secret'
    DJANGO_ADMIN_USER=admin DJANGO_ADMIN_PASSWORD=secret python manage.py create_admin
"""
from __future__ import annotations

import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update the Studio admin (staff + superuser)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.environ.get("DJANGO_ADMIN_USER"))
        parser.add_argument("--password", default=os.environ.get("DJANGO_ADMIN_PASSWORD"))
        parser.add_argument("--email", default=os.environ.get("DJANGO_ADMIN_EMAIL", ""))

    def handle(self, *args, **opts):
        username = (opts.get("username") or "").strip()
        password = opts.get("password") or ""
        if not username or not password:
            raise CommandError(
                "provide --username and --password (or DJANGO_ADMIN_USER / "
                "DJANGO_ADMIN_PASSWORD env vars)"
            )
        user, created = User.objects.get_or_create(username=username)
        user.email = opts.get("email") or user.email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} admin '{username}'."))
