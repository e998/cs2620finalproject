import pytest
from app import create_app # Assuming your Flask app factory is in app/__init__.py
# Import db from where it's defined (adjust path if needed)
try:
    from shared.extensions import db as _db # Alias to avoid conflict
except ImportError:
    print("Warning: Could not import db from shared.extensions. DB fixtures will not work.")
    _db = None

@pytest.fixture(scope='session') # Use session scope for app setup
def app():
    """Create and configure a new app instance for the test session."""
    test_config = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        # Use a separate database for testing (e.g., in-memory SQLite)
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        # Suppress track modifications warning
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    }
    _app = create_app(test_config=test_config)

    # Establish an application context before creating tables
    with _app.app_context():
        if _db:
            # Make sure tables are created based on models known to db
            # You might need to ensure all models are imported where db is defined
            # or within create_app() before this point.
            _db.create_all() # Create database tables

    yield _app # Provide the app instance to tests

    # Teardown: Drop database tables after the session
    with _app.app_context():
         if _db:
            _db.session.remove() # Close session
            _db.drop_all()     # Drop tables

@pytest.fixture(scope='function') # Use function scope for client & transaction rollback
def client(app):
    """A test client for the app, with transaction rollback."""
    with app.test_client() as client:
        # Start a transaction for each test
        if _db:
            with app.app_context():
                # Begin a nested transaction (useful for DBs supporting it)
                # For SQLite, session.rollback() is the main mechanism
                _db.session.begin_nested()

        yield client # Provide the client to the test function

        # Rollback the transaction after the test
        if _db:
             with app.app_context():
                _db.session.rollback() # Roll back any changes made during the test
