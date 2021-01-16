"""Example app."""

import muffin
import random


app = muffin.Application('sessions', SESSION_SECRET_KEY='EXAMPLE_KEY', SESSION_AUTO_MANAGE=True)


@app.route('/')
async def index(request):
    """Return JSON with current user session."""
    return dict(request.session)


@app.route('/update')
async def update(request):
    """Update a current user's session."""
    request.session['random'] = random.random()
    return muffin.ResponseRedirect('/')
