from contextlib import contextmanager

from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from authlib.integrations.flask_client import OAuth
from google.cloud import ndb as _ndb


class NDB:
    """Flask glue for google-cloud-ndb (Firestore in Datastore mode).

    Every datastore call needs an active NDB context. Requests get one from
    a WSGI middleware; CLI commands and tests use ``ndb.context()``. The
    client is created lazily so importing/creating the app never needs
    Google credentials (e.g. in unit tests against the emulator).
    """

    def __init__(self):
        self._client = None
        self._project = None

    def init_app(self, app):
        self._project = app.config.get("GOOGLE_CLOUD_PROJECT") or None
        app.wsgi_app = _NDBContextMiddleware(app.wsgi_app, self)
        app.extensions["ndb"] = self

    @property
    def client(self):
        if self._client is None:
            self._client = _ndb.Client(project=self._project)
        return self._client

    @contextmanager
    def context(self):
        """Reuse the current thread's context if there is one (NDB forbids
        nesting), otherwise open a fresh one."""
        if _ndb.get_context(False) is not None:
            yield
            return
        with self.client.context():
            yield


class _NDBContextMiddleware:
    def __init__(self, wsgi_app, ndb_ext):
        self.wsgi_app = wsgi_app
        self.ndb_ext = ndb_ext

    def __call__(self, environ, start_response):
        with self.ndb_ext.context():
            return self.wsgi_app(environ, start_response)


ndb = NDB()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
mail = Mail()
oauth = OAuth()

login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"
