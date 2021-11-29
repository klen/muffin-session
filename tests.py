import muffin
import pytest


SECRET = 'SECRET-TESTS'


@pytest.fixture
def app():
    return muffin.Application(DEBUG=True, SESSION_LOGIN_URL='/home')


@pytest.mark.parametrize('ses_type', ['base64', 'jwt', 'fernet'])
async def test_session_manual(app, client, ses_type):
    from muffin_session import Plugin as Session

    session = Session(app, secret_key=SECRET, session_type=ses_type)
    assert session.cfg.secret_key == SECRET
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


@pytest.mark.parametrize('ses_type', ['base64', 'jwt', 'fernet'])
async def test_session_middleware(app, client, ses_type):
    from muffin_session import Plugin as Session

    session = Session(app, auto_manage=True, secret_key=SECRET, session_type=ses_type)
    assert session.cfg.auto_manage
    assert session.cfg.secret_key == SECRET

    @app.middleware
    async def custom_md(handler, request, receive, send):
        assert request.session is not None
        return await handler(request, receive, send)

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


@pytest.mark.parametrize('ses_type', ['base64', 'jwt', 'fernet'])
def test_session_save(app, client, ses_type):
    from muffin_session import Plugin

    session = Plugin(app, secret_key=SECRET, session_type=ses_type)
    scope = client.build_scope('/', method='GET')
    request = muffin.Request(scope)

    response = session.save_to_response(request, {'test': 42}, id=1)
    assert response
    assert isinstance(response, muffin.ResponseJSON)
    header = response.headers['Set-Cookie']
    assert header

    token = header.split(';')[0].split('=', 1)[1]
    ses = session.create_from_token(token)
    assert ses['id'] == 1


@pytest.mark.parametrize('ses_type', ['base64', 'jwt', 'fernet'])
def test_session_login(app, client, ses_type):
    from muffin_session import Plugin

    session = Plugin(app, secret_key=SECRET, session_type=ses_type)

    scope = client.build_scope('/', method='GET')
    request = muffin.Request(scope)

    response = session.login(request, 42, response='OK')
    header = response.headers['Set-Cookie']
    assert header

    token = header.split(';')[0].split('=', 1)[1]
    ses = session.create_from_token(token)
    assert ses['id'] == 42


@pytest.mark.parametrize('ses_type', ['base64', 'jwt', 'fernet'])
async def test_user_pass(app, client, ses_type):
    from muffin_session import Plugin as Session

    session = Session(app, secret_key=SECRET, session_type=ses_type)

    @app.route('/login')
    async def login(request):
        session.login(request, request.url.query.get('name'))
        return session.save_to_response(request.session, res)

    @app.route('/')
    async def anonimous(request):
        return 'ANON'

    @app.route('/user-required-redirect')
    @session.user_pass()
    async def user_required(request):
        return 'user-required-redirect'

    @app.route('/user-required-404')
    @session.user_pass(location=muffin.ResponseError.NOT_FOUND())
    async def user_required_404(request):
        return 'user-required-404'

    res = await client.get('/', follow_redirect=False)
    assert res.status_code == 200
    assert await res.text() == 'ANON'

    res = await client.get('/user-required-redirect', follow_redirect=False)
    assert res.status_code == 307

    res = await client.get('/user-required-404', follow_redirect=False)
    assert res.status_code == 404


async def test_redirect_html(app, client):
    from muffin_session import Plugin as Session, ResponseHTMLRedirect

    session = Session(app, secret_key=SECRET, redirect_type=ResponseHTMLRedirect)

    @app.route('/')
    @session.user_pass(location='/login')
    async def anonimous(request):
        return 'ANON'

    res = await client.get('/')
    assert res.status_code == 200
    text = await res.text()
    assert text
    assert "/login" in text
