"""Support session with Muffin framework."""

import functools
import sys
import typing as t
from inspect import iscoroutine, isawaitable

from asgi_sessions import Session, SessionJWT, SessionFernet
from asgi_tools.response import parse_response
from muffin import Application, ResponseRedirect, Response, Request, ResponseError
from muffin.plugins import BasePlugin
from muffin.typing import Receive, Send, ASGIApp


__version__ = "2.0.0"
__project__ = "muffin-session"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


SESSION_KEY = 'session'
USER_KEY = 'user'

F = t.TypeVar('F', bound=t.Callable)


class Plugin(BasePlugin):

    """Provide session's engine for Muffin."""

    name = 'session'
    defaults: t.Dict = {
        'auto_manage': False,
        'session_type': 'jwt',
        'secret_key': 'InsecureSecret',  # Secret is using for secure the session
        'cookie_name': 'session',
        'cookie_params': {
            'path': '/',
            'max-age': None,  # Defines the lifetime of the session-cookie, in seconds
            'samesite': 'lax',
            'secure': False,
        },

        'default_user_checker': lambda x: x,
        'login_url': '/login',
    }

    # XXX: Python 3.7 (py37)
    if sys.version_info < (3, 8):
        del defaults['cookie_params']['samesite']

    def setup(self, app: Application, **options):
        """Initialize the plugin."""
        super().setup(app, **options)

        if self.cfg.secret_key == 'InsecureSecret':
            app.logger.warning(
                'Use insecure secret key. '
                'Change SESSION_SECRET_KEY option in your app configuration.')

        self._user_loader = lambda id_: id_  # noqa

        # Install middleware if auto managed
        if self.cfg.auto_manage:
            app.middleware(self.__middleware)

    async def __middleware(
            self, handler: ASGIApp, request: Request, receive: Receive, send: Send):
        """Session auto load middleware, connecting from configuration."""
        session = self.load_from_request(request)
        response = await handler(request, receive, send)
        if session.modified and isinstance(response, Response):
            self.save_to_response(session, response)

        return response

    def user_loader(self, func: F) -> F:
        """Register a function as user loader."""
        self._user_loader = func  # noqa
        return func

    def load_from_request(self, request: Request) -> Session:
        """Load a session from the request."""
        if SESSION_KEY not in request:
            request[SESSION_KEY] = self.create_from_token(
                request.cookies.get(self.cfg.cookie_name))

        return request[SESSION_KEY]

    def create_from_token(self, token: str = None) -> Session:
        """Create a session from the given token."""
        cfg = self.cfg
        ses_type = cfg.session_type
        if ses_type == 'jwt':
            return SessionJWT(token, secret=cfg.secret_key)

        if ses_type == 'fernet':
            return SessionFernet(token, secret=cfg.secret_key)

        return Session(token)

    def save_to_response(
            self, obj: t.Union[Session, Request], response: t.Any, **changes) -> Response:
        """Save session to response cookies."""
        if isinstance(obj, Request):
            obj = self.load_from_request(obj)
        for name, value in changes.items():
            obj[name] = value
        if not isinstance(response, Response):
            response = parse_response(response)
        response.headers['Set-Cookie'] = obj.cookie(self.cfg.cookie_name, self.cfg.cookie_params)
        return response

    async def load_user(self, request):
        """Load user from request."""
        if USER_KEY not in request:
            session = self.load_from_request(request)
            if 'id' not in session:
                return

            user = self._user_loader(session['id'])
            if isawaitable(user):
                user = await user
            request[USER_KEY] = user

        return request[USER_KEY]

    def user_pass(self, checker: t.Callable = None,
                  location: t.Union[str, t.Callable[[Request], str], ResponseError] = None,
                  **rkwargs):
        """Check that a user is logged and pass conditions."""
        def wrapper(view):

            @functools.wraps(view)
            async def handler(request, *args, **kwargs):
                await self.check_user(request, checker, location, **rkwargs)
                return await view(request, *args, **kwargs)

            return handler

        return wrapper

    async def check_user(
            self, request: Request, checker: t.Callable = None,
            location: t.Union[str, t.Callable] = None, **response_params) -> t.Any:
        """Check for user is logged and pass the given checker.

        :param checker: user checker function, defaults to default_user_checker
        :param location: where to redirect if user is not logged in.
            May be either string (URL) or function which accepts request as argument
            and returns string URL.
        """
        user = await self.load_user(request)
        checker = checker or self.cfg.default_user_checker
        if not checker(user):
            redirect = location or self.cfg.login_url
            if isinstance(redirect, ResponseError):
                raise redirect

            if callable(redirect):
                redirect = redirect(request)
                if iscoroutine(redirect):
                    redirect = await redirect
            raise ResponseRedirect(redirect, **response_params)

        return user

    def login(self, request: Request, ident: str, *, response: t.Any = None):
        """Store user ID in the session."""
        ses = self.load_from_request(request)
        ses['id'] = ident
        if response is not None:
            return self.save_to_response(ses, response)

    def logout(self, request: Request, *, response: t.Any = None):
        """Logout an user."""
        ses = self.load_from_request(request)
        if 'id' in ses:
            del ses['id']
        if response is not None:
            return self.save_to_response(ses, response)
