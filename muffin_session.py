"""Support session with Muffin framework."""

# Package information
# ===================
import asyncio
import base64
import functools
import time

import ujson as json
from muffin import HTTPFound, Response
from muffin.plugins import BasePlugin
from muffin.utils import create_signature, check_signature, to_coroutine


__version__ = "0.4.0"
__project__ = "muffin-session"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "MIT"


SESSION_KEY = 'session'
USER_KEY = 'user'
FLASHES_KEY = '_flashes'


@asyncio.coroutine
def session_autoload_middleware_factory(app, handler):
    """Create middleware for auto loading sessions."""
    sessions = app.ps.session

    @asyncio.coroutine
    def session_autoload_middleware(request):
        """Load a session to request."""
        yield from sessions.load(request)
        return (yield from handler(request))

    return session_autoload_middleware


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
            app.middlewares.append(session_autoload_middleware_factory)

        if 'jinja2' in app.ps:
            app.ps.jinja2.register(self.get_flashed_messages)

    def user_loader(self, func):
        """Register a function as user loader."""
        self._user_loader = to_coroutine(func)  # noqa
        return self._user_loader

    @asyncio.coroutine
    def load(self, request):
        """Load session from cookies."""
        if SESSION_KEY not in request:
            session = Session(self.cfg.secret, max_age=self.cfg.max_age, domain=self.cfg.domain)
            session.load(request.cookies)
            self.app.logger.debug('Session loaded: %s', session)
            request[SESSION_KEY] = request.session = session
        return request[SESSION_KEY]

    __call__ = load

    def save(self, request, response):
        """Save session to response cookies."""
        if isinstance(response, Response) and SESSION_KEY in request and not response.started:
            session = request[SESSION_KEY]
            if session.save(response.set_cookie):
                self.app.logger.debug('Session saved: %s', session)

    @asyncio.coroutine
    def load_user(self, request):
        """Load user from request."""
        if USER_KEY not in request:
            session = yield from self.load(request)
            if 'id' not in session:
                return None

            request[USER_KEY] = request.user = yield from self._user_loader(session['id'])

        return request[USER_KEY]

    @asyncio.coroutine
    def check_user(self, request, func=None, location=None, **kwargs):
        """Check for user is logged and pass the given func.

        :param func: user checker function, defaults to default_user_checker
        :param location: where to redirect if user is not logged in.
            May be either string (URL) or function which accepts request as argument
            and returns string URL.
        """
        user = yield from self.load_user(request)
        func = func or self.cfg.default_user_checker
        if not func(user):
            location = location or self.cfg.login_url
            while callable(location):
                location = location(request)
                while asyncio.iscoroutine(location):
                    location = yield from location
            raise HTTPFound(location, **kwargs)
        return user

    def user_pass(self, func=None, location=None, **rkwargs):
        """Decorator ensures that user pass the given func."""
        def wrapper(view):
            view = to_coroutine(view)

            @asyncio.coroutine
            @functools.wraps(view)
            def handler(request, *args, **kwargs):
                yield from self.check_user(request, func, location, **rkwargs)
                return (yield from view(request, *args, **kwargs))
            return handler

        return wrapper

    @asyncio.coroutine
    def login(self, request, id_):
        """Login an user by ID."""
        session = yield from self.load(request)
        session['id'] = id_

    @asyncio.coroutine
    def logout(self, request):
        """Logout an user."""
        session = yield from self.load(request)
        if 'id' in session:
            del session['id']

    @asyncio.coroutine
    def flash(self, request, message, category='message'):
        """Add a message to be flashes on next request."""
        session = yield from self.load(request)
        flashes = session.get(FLASHES_KEY, [])
        if isinstance(flashes, str):
            flashes = json.loads(flashes)
        flashes.append((category, message))
        session[FLASHES_KEY] = flashes

    @staticmethod
    def get_flashed_messages(session, with_categories=False, category_filter=None):
        """Retrieve flashed messages.

        Important: this is not a coroutine, and as such it requires you to
        call `app.ps.session.load` beforehand!

        For example, if you call `load_user` then it is okay.

        Or you can use async version of this method.

        First argument can be either already-loaded Session
        or a request object (if session was loaded before).
        """
        if not isinstance(session, Session):
            # this is probably a request; try to get session from it
            request = session
            if SESSION_KEY not in request:
                raise ValueError('Please call `await app.ps.session.load(request)` beforehand!')
            session = request[SESSION_KEY]

        flashes = session.pop(FLASHES_KEY, [])
        if isinstance(flashes, str):
            flashes = json.loads(flashes)

        if category_filter:
            flashes = list(filter(lambda f: f[0] in category_filter, flashes))

        if not with_categories:
            return [f[1] for f in flashes]

        return flashes

    @asyncio.coroutine
    def get_flashed_messages_async(self, request, with_categories=False, category_filter=None):
        """Retrieve flashed messages.

        This is a coroutine, and it will load session if needed.
        """
        session = yield from self.load(request)
        return self.get_flashed_messages(session, with_categories, category_filter)


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
