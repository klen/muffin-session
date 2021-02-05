import muffin
import pytest


@pytest.fixture(params=[
    pytest.param('asyncio'),
    pytest.param('trio'),
], autouse=True)
def anyio_backend(request):
    return request.param


@pytest.fixture
def app():
    return muffin.Application('session', DEBUG=True, SESSION_LOGIN_URL='/home')


async def test_session_manual(app, client):
    from muffin_session import Plugin as Session

    session = Session(app, secret_key='123456')
    assert session.cfg.login_url == '/home'

    @app.route('/auth')
    @session.user_pass()
    async def auth(request):
        return request.user

    res = await client.get('/auth', follow_redirect=False)
    assert res.status_code == 307
    assert res.headers['location'] == '/home'

    @app.route('/auth_dyn')
    @session.user_pass(location=lambda req: req.url.query.get('target'))
    async def auth_dyn(request):
        return request.user

    res = await client.get('/auth_dyn', query={'target': '/another_page'}, follow_redirect=False)
    assert res.status_code == 307
    assert res.headers['location'] == '/another_page'

    async def determine_redir_async(request):
        return request.url.query.get('target')

    @app.route('/auth_dyn_async')
    @session.user_pass(location=determine_redir_async)
    async def auth_dyn_async(request):
        return request.user

    res = await client.get(
        '/auth_dyn_async', query={'target': '/another_page'}, follow_redirect=False)
    assert res.status_code == 307
    assert res.headers['location'] == '/another_page'

    @app.route('/login')
    async def login(request):
        session.login(request, request.url.query.get('name'))
        res = muffin.ResponseRedirect('/auth', status_code=302)
        session.save_to_response(request.session, res)
        return res

    res = await client.get('/login', query={'name': 'mike'})
    assert res.status_code == 200
    text = await res.text()
    assert 'mike' in text

    @app.route('/session')
    async def get_session(request):
        ses = session.load_from_request(request)
        return dict(ses)

    res = await client.get('/session')
    assert res.status_code == 200
    assert await res.json() == {'id': 'mike'}

    @app.route('/error')
    async def error(request):
        ses = session.load_from_request(request)
        ses = session.load_from_request(request)
        ses['name'] = 'value'
        res = muffin.ResponseError(status_code=403)
        session.save_to_response(ses, res)
        return res

    res = await client.get('/error')
    assert res.status_code == 403

    res = await client.get('/session')
    assert res.status_code == 200
    json = await res.json()
    assert 'name' in json

    @app.route('/logout')
    async def logout(request):
        session.logout(request)
        res = muffin.ResponseRedirect('/', status_code=302)
        session.save_to_response(request.session, res)
        return res

    await client.get('/logout')
    res = await client.get('/session')
    json = await res.json()
    assert 'id' not in json

    res = await client.get('/auth', follow_redirect=False)
    assert res.status_code == 307
    assert res.headers['location'] == '/home'

    res = await client.get('/logout', follow_redirect=False)
    assert res.status_code == 302
    assert res.headers['location'] == '/'


async def test_session_middleware(app, client):
    from muffin_session import Plugin as Session

    Session(app, auto_manage=True, secret_key='123456')

    @app.route('/session')
    async def auth(request):
        return dict(request.session)

    res = await client.get('/session')
    assert res.status_code == 200
    assert await res.json() == {}

    @app.route('/login')
    async def login(request):
        request.session['user'] = 'mike'
        return muffin.ResponseRedirect('/session')

    res = await client.get('/login')
    assert res.status_code == 200
    assert await res.json() == {'user': 'mike'}
