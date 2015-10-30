"""Example app."""

import muffin
import random


app = muffin.Application(
    'sessions',

    PLUGINS=('muffin_session',),

    LOG_LEVEL='DEBUG',
)


@app.register('/')
def index(request):
    """Return JSON with current user session."""
    return (yield from app.ps.session.load(request))


@app.register('/update')
def update(request):
    """Update a current user's session."""
    session = yield from app.ps.session.load(request)
    session['random'] = random.random()
    return session


if __name__ == '__main__':
    app.manage()
