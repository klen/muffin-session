"""Support session with Muffin framework."""

from __future__ import annotations

import functools
from inspect import isawaitable, iscoroutine
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import quote_plus

from asgi_sessions import Session, SessionFernet, SessionJWT
from asgi_tools.response import ResponseHTML, parse_response
from muffin import Application, Request, Response, ResponseError, ResponseRedirect
from muffin.plugins import BasePlugin

if TYPE_CHECKING:
    from asgi_tools.types import TASGIReceive, TASGISend, TVCallable

SESSION_KEY = "session"
USER_KEY = "user"

__all__ = "Plugin", "ResponseHTMLRedirect"


class Plugin(BasePlugin):
    """Provide session's engine for Muffin."""

    name = "session"
    defaults = {
        "auto_manage": False,
        "session_type": "jwt",
        "secret_key": "InsecureSecret",  # Secret is using for secure the session
        "cookie_name": "session",
        "cookie_params": {
            "path": "/",
            "max-age": None,  # Defines the lifetime of the session-cookie, in seconds
            "samesite": "lax",
            "secure": False,
        },
        "default_user_checker": lambda x: x,
        "login_url": "/login",
        "redirect_type": ResponseRedirect,
    }

    def setup(self, app: Application, **options):
        """Initialize the plugin."""
        super().setup(app, **options)

        if self.cfg.secret_key == "InsecureSecret":  # noqa: S105
            app.logger.warning(
                "Use insecure secret key. "
                "Change SESSION_SECRET_KEY option in your app configuration."
            )

        self._user_loader = lambda id_: id_

        # Install middleware if auto managed
        if self.cfg.auto_manage:
            app.middleware(self.__middleware)

    async def __middleware(
        self,
        handler: Callable,
        request: Request,
        receive: TASGIReceive,
        send: TASGISend,
    ) -> Response:
        """Session auto load middleware, connecting from configuration."""
        session = self.load_from_request(request)
        response = await handler(request, receive, send)
        if session.modified and isinstance(response, Response):
            self.save_to_response(session, response)

        return response

    def user_loader(self, func: TVCallable) -> TVCallable:
        """Register a function as user loader."""
        self._user_loader = func
        return func

    def load_from_request(self, request: Request) -> Session:
        """Load a session from the request."""
        if SESSION_KEY not in request:
            request[SESSION_KEY] = self.create_from_token(
                request.cookies.get(self.cfg.cookie_name)
            )

        return request[SESSION_KEY]

    def create_from_token(self, token: str | None = None) -> Session:
        """Create a session from the given token."""
        cfg = self.cfg
        ses_type = cfg.session_type
        if ses_type == "jwt":
            return SessionJWT(token, secret=cfg.secret_key)

        if ses_type == "fernet":
            return SessionFernet(token, secret=cfg.secret_key)

        return Session(token)

    def save_to_response(self, obj: Session | Request, response, **changes) -> Response:
        """Save session to response cookies."""
        if isinstance(obj, Request):
            obj = self.load_from_request(obj)
        for name, value in changes.items():
            obj[name] = value
        if not isinstance(response, Response):
            response = parse_response(response)
        response.headers["Set-Cookie"] = obj.cookie(
            self.cfg.cookie_name, self.cfg.cookie_params
        )
        return response

    async def load_user(self, request: Request) -> Any:
        """Load user from request."""
        if USER_KEY not in request:
            session = self.load_from_request(request)
            if "id" not in session:
                return None

            user = self._user_loader(session["id"])
            if isawaitable(user):
                user = await user
            request[USER_KEY] = user

        return request[USER_KEY]

    def user_pass(
        self,
        checker: Callable | None = None,
        location: str | Callable[[Request], str] | ResponseError | None = None,
        **rkwargs,
    ) -> Callable[[Callable], Callable]:
        """Check that a user is logged and pass conditions."""

        def wrapper(view):
            @functools.wraps(view)
            async def handler(request, *args, **kwargs):
                await self.check_user(request, checker, location, **rkwargs)
                return await view(request, *args, **kwargs)

            return handler

        return wrapper

    async def check_user(
        self,
        request: Request,
        checker: Callable | None = None,
        location: str | Callable | None = None,
        **response_params,
    ):
        """Check for user is logged and pass the given checker.

        :param checker: user checker function, defaults to default_user_checker
        :param location: where to redirect if user is not logged in.
            May be either string (URL) or function which accepts request as argument
            and returns string URL.
        """
        user = await self.load_user(request)
        checker = checker or self.cfg.default_user_checker
        assert callable(checker), "Checker must be a callable"
        if not checker(user):
            redirect = location or self.cfg.login_url
            if isinstance(redirect, ResponseError):
                raise redirect

            if callable(redirect):
                redirect = redirect(request)
                if iscoroutine(redirect):
                    redirect = await redirect
            raise self.cfg.redirect_type(redirect, **response_params)

        return user

    def login(
        self, request: Request, ident: Any, *, response: Any = None
    ) -> Response | None:
        """Store user ID in the session."""
        ses = self.load_from_request(request)
        ses["id"] = ident
        if response is not None:
            return self.save_to_response(ses, response)
        return response

    def logout(self, request: Request, *, response: Any = None) -> Response | None:
        """Logout an user."""
        ses = self.load_from_request(request)
        if "id" in ses:
            del ses["id"]
        if response is not None:
            return self.save_to_response(ses, response)
        return response


class ResponseHTMLRedirect(ResponseHTML, BaseException):
    """Make redirect through HTML to save coookies."""

    def __init__(
        self,
        location: str,
        status_code: int | None = None,
        headers: dict | None = None,
        content_type: str | None = None,
    ):
        """Prepare a content from the given location."""
        content = (
            "<html><head>"
            f'<meta http-equiv="Refresh" content="0; URL={location}" />'
            f'<script>window.location = "{location}"</script></head>'
            f'<body>Please click <a href="{location}">here</a> '
            "if you are not redirected within a few seconds"
            "</body></html>"
        )
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            content_type=content_type,
        )
        self.headers["location"] = quote_plus(location, safe=":/%#?&=@[]!$&'()*+,;")
