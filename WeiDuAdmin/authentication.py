# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from rest_framework.authentication import SessionAuthentication

from WeiDuAdmin import settings


class WdSessionAuthentication(SessionAuthentication):

    def authenticate(self, request):
        # Get the session-based user from the underlying HttpRequest object
        user = getattr(request._request, 'user', None)

        # Unauthenticated, CSRF validation not required
        if not user or not user.is_active:
            return None
        if not settings.DEBUG:  # or request.get_host().find(settings.CSRF_COOKIE_DOMAIN) > -1:
            # TODO: DEBUG = False need test
            self.enforce_csrf(request)

        # CSRF passed with authenticated user
        return (user, None)