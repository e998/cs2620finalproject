import pytest
from shared.models import Activity
from shared.extensions import db
from datetime import datetime

@pytest.fixture
def clean_activity_table(app):
    with app.app_context():
        db.session.query(Activity).delete()
        db.session.commit()
    yield
    with app.app_context():
        db.session.query(Activity).delete()
        db.session.commit()

def test_add_activity_log(app, clean_activity_table):
    """Test adding an activity log entry to the Activity table."""
    with app.app_context():
        log = Activity(label='TestEvent', activitytime=datetime.utcnow())
        db.session.add(log)
        db.session.commit()
        found = Activity.query.filter_by(label='TestEvent').first()
        assert found is not None
        assert found.label == 'TestEvent'

def test_query_activity_logs(app, clean_activity_table):
    """Test querying multiple activity log entries."""
    with app.app_context():
        db.session.add(Activity(label='EventA', activitytime=datetime.utcnow()))
        db.session.add(Activity(label='EventB', activitytime=datetime.utcnow()))
        db.session.commit()
        logs = Activity.query.order_by(Activity.activitytime.desc()).all()
        labels = [log.label for log in logs]
        assert 'EventA' in labels
        assert 'EventB' in labels

def test_clear_activity_logs(app, clean_activity_table):
    """Test clearing all activity logs."""
    with app.app_context():
        db.session.add(Activity(label='EventC', activitytime=datetime.utcnow()))
        db.session.commit()
        assert Activity.query.count() > 0
        db.session.query(Activity).delete()
        db.session.commit()
        assert Activity.query.count() == 0