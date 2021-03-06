"""Support session with Muffin framework."""

import sys
import functools
import typing as t
from inspect import iscoroutine

from asgi_sessions import Session
from asgi_tools.middleware import ASGIApp
from asgi_tools._types import Receive, Send
import muffin
from muffin import ResponseRedirect, Response, Request
from muffin.plugin import BasePlugin
from muffin.utils import to_awaitable


__version__ = "0.10.0"
__project__ = "muffin-session"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


SESSION_KEY = 'session'
USER_KEY = 'user'


class Plugin(BasePlugin):

    """Provide session's engine for Muffin."""

    name = 'session'
    defaults: t.Dict = {
        'auto_manage': False,
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

    # XXX: Python 3.7
    if sys.version_info < (3, 8):
        del defaults['cookie_params']['samesite']

    def setup(self, app: muffin.Application, **options):
        """Initialize the plugin."""
        super().setup(app, **options)

        if self.cfg.secret_key == 'InsecureSecret':
            app.logger.warning(
                'Use insecure secret key. '
                'Change SESSION_SECRET_KEY option in your app configuration.')

        self._user_loader = to_awaitable(lambda id_: id_)  # noqa

        # Install middleware if auto managed
        if self.cfg.auto_manage:
            app.middleware(self.__middleware)

    async def __middleware(
            self, handler: ASGIApp, request: Request, receive: Receive, send: Send):
        """Session auto load middleware, connecting from configuration."""
        session = self.load_from_request(request)
        response = await handler(request, receive, send)
        if not session.pure and isinstance(response, Response):
            self.save_to_response(session, response)

        return response

    def load_from_request(self, request: Request) -> Session:
        """Load a session from the request."""
        if SESSION_KEY not in request:
            session = Session(self.cfg.secret_key, token=request.cookies.get(self.cfg.cookie_name))
            request[SESSION_KEY] = session

        return request[SESSION_KEY]

    def save_to_response(self, session: Session, response: Response):
        """Save session to response cookies."""
        response.headers['Set-Cookie'] = session.cookie(
            self.cfg.cookie_name, self.cfg.cookie_params)

    def user_loader(self, func):
        """Register a function as user loader."""
        self._user_loader = to_awaitable(func)  # noqa
        return func

    async def load_user(self, request):
        """Load user from request."""
        if USER_KEY not in request:
            session = self.load_from_request(request)
            if 'id' not in session:
                return

            request[USER_KEY] = await self._user_loader(session['id'])

        return request[USER_KEY]

    def user_pass(self, func=None, location=None, **rkwargs):
        """Check that a user is logged and pass conditions."""
        def wrapper(view):

            @functools.wraps(view)
            async def handler(request, *args, **kwargs):
                await self.check_user(request, func, location, **rkwargs)
                return await view(request, *args, **kwargs)

            return handler

        return wrapper

    async def check_user(
            self, request: Request, func: t.Callable = None,
            location: t.Union[str, t.Callable] = None, **response_params) -> t.Any:
        """Check for user is logged and pass the given func.

        :param func: user checker function, defaults to default_user_checker
        :param location: where to redirect if user is not logged in.
            May be either string (URL) or function which accepts request as argument
            and returns string URL.
        """
        user = await self.load_user(request)
        func = func or self.cfg.default_user_checker
        if not func(user):
            redirect_url = location or self.cfg.login_url
            while callable(redirect_url):
                redirect_url = redirect_url(request)
                while iscoroutine(redirect_url):
                    redirect_url = await redirect_url
            raise ResponseRedirect(redirect_url, **response_params)
        return user

    def login(self, request: Request, ident: str):
        """Store user ID in the session."""
        session = self.load_from_request(request)
        session['id'] = ident

    def logout(self, request: Request):
        """Logout an user."""
        session = self.load_from_request(request)
        if 'id' in session:
            del session['id']
