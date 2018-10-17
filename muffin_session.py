"""Support session with Muffin framework."""

# Package information
# ===================
import asyncio
import base64
import functools
import time
from aiohttp.web import middleware

import ujson as json
from muffin import HTTPFound, Response
from muffin.plugins import BasePlugin
from muffin.utils import create_signature, check_signature, to_coroutine


__version__ = "0.6.0"
__project__ = "muffin-session"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


SESSION_KEY = 'session'
USER_KEY = 'user'


class Plugin(BasePlugin):

    """Provide session's engine for Muffin."""

    name = 'session'
    defaults = {
        'auto_load': False,
        'default_user_checker': lambda x: x,
        'login_url': '/login',
        'secret': 'InsecureSecret',  # Secret is using for secure the session
        'max_age': None,  # Defines the lifetime of the session-cookie, in seconds
        'domain': None,  # Defines session-cookie domain
        'session_cookie': 'session',
    }

    def setup(self, app):
        """Initialize the plugin."""
        super().setup(app)

        if self.cfg.secret == 'InsecureSecret':
            app.logger.warn(
                'Use insecure secret key. Change SESSION_SECRET option in configuration.')

        self._user_loader = asyncio.coroutine(lambda id_: id_)  # noqa

        app.on_response_prepare.append(self.save)

        if self.cfg.auto_load:
            app.middlewares.append(self._middleware)

    async def _middleware(self, request, handler):
        """Session auto load middleware, connecting from configuration."""
        await self.load(request)
        return await handler(request)

    _middleware.__middleware_version__ = 1

    def user_loader(self, func):
        """Register a function as user loader."""
        self._user_loader = to_coroutine(func)  # noqa
        return self._user_loader

    async def load(self, request):
        """Load session from cookies."""
        if SESSION_KEY not in request:
            session = Session(self.cfg.secret, key=self.cfg.session_cookie,
                              max_age=self.cfg.max_age, domain=self.cfg.domain)
            session.load(request.cookies)
            self.app.logger.debug('Session loaded: %s', session)
            request[SESSION_KEY] = request.session = session
        return request[SESSION_KEY]

    __call__ = load

    async def save(self, request, response):
        """Save session to response cookies."""
        if isinstance(response, Response) and SESSION_KEY in request and not response.prepared:
            session = request[SESSION_KEY]
            if session.save(response.set_cookie):
                self.app.logger.debug('Session saved: %s', session)

    async def load_user(self, request):
        """Load user from request."""
        if USER_KEY not in request:
            session = await self.load(request)
            if 'id' not in session:
                return None

            request[USER_KEY] = request.user = await self._user_loader(session['id'])

        return request[USER_KEY]

    async def check_user(self, request, func=None, location=None, **kwargs):
        """Check for user is logged and pass the given func.

        :param func: user checker function, defaults to default_user_checker
        :param location: where to redirect if user is not logged in.
            May be either string (URL) or function which accepts request as argument
            and returns string URL.
        """
        user = await self.load_user(request)
        func = func or self.cfg.default_user_checker
        if not func(user):
            location = location or self.cfg.login_url
            while callable(location):
                location = location(request)
                while asyncio.iscoroutine(location):
                    location = await location
            raise HTTPFound(location, **kwargs)
        return user

    def user_pass(self, func=None, location=None, **rkwargs):
        """Decorator ensures that user pass the given func."""
        def wrapper(view):
            view = to_coroutine(view)

            @functools.wraps(view)
            async def handler(request, *args, **kwargs):
                await self.check_user(request, func, location, **rkwargs)
                return await view(request, *args, **kwargs)
            return handler

        return wrapper

    async def login(self, request, id_):
        """Login an user by ID."""
        session = await self.load(request)
        session['id'] = id_

    async def logout(self, request):
        """Logout an user."""
        session = await self.load(request)
        if 'id' in session:
            del session['id']


class Session(dict):

    """Implement session interface."""

    encoding = 'utf-8'

    def __init__(self, secret, key='session.id', **params):
        """Initialize the session."""
        super(Session, self).__init__()
        self.secret = secret.encode(self.encoding)
        self.key = key
        self.params = params
        self.store = {}

    def save(self, set_cookie, **params):
        """Update cookies if the session has been changed."""
        if set(self.store.items()) ^ set(self.items()):
            value = dict(self.items())
            value = json.dumps(value)
            value = self.encrypt(value)
            if not isinstance(value, str):
                value = value.encode(self.encoding)
            set_cookie(self.key, value, **self.params)
            return True
        return False

    def __setitem__(self, name, value):
        """Dump value to JSON."""
        if isinstance(value, (dict, list, tuple, set)):
            value = json.dumps(value)
        super().__setitem__(name, value)

    def load(self, cookies, **kwargs):
        """Load session from cookies."""
        value = cookies.get(self.key, None)
        if value is None:
            return False

        value = self.decrypt(value)
        if not value:
            return False

        data = json.loads(value)
        if not isinstance(data, dict):
            return False

        self.store = data
        self.update(self.store)

    def encrypt(self, value):
        """Encrypt session data."""
        timestamp = str(int(time.time()))
        value = base64.b64encode(value.encode(self.encoding))
        signature = create_signature(self.secret, value + timestamp.encode(),
                                     encoding=self.encoding)
        return "|".join([value.decode(self.encoding), timestamp, signature])

    def decrypt(self, value):
        """Decrypt session data."""
        value, timestamp, signature = value.split("|")
        if check_signature(signature, self.secret, value + timestamp, encoding=self.encoding):
            return base64.b64decode(value).decode(self.encoding)
        return 'null'
