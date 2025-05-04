from flask import Blueprint, jsonify, render_template, redirect, url_for, flash, request, session, g
from datetime import datetime, timedelta
from sqlalchemy import func, Integer, text
import time
from collections import defaultdict

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.models import Order, Clients, Activity

from dotenv import load_dotenv
from health import create_healthapp
from app import db, socketio

load_dotenv()

healthapp = Blueprint('healthapp', __name__)

# --- Metrics Storage ---
api_metrics = defaultdict(lambda: {'count': 0, 'total_time': 0.0})

# --- Decorator for API metrics ---
def record_api_metrics(endpoint):
    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                api_metrics[endpoint]['count'] += 1
                api_metrics[endpoint]['total_time'] += elapsed
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

@healthapp.route("/")
@record_api_metrics('index')
def index():
    return render_template("health.html", data={})

@healthapp.route("/cluster_status")
@record_api_metrics('cluster_status')
def get_cluster_status():
    clients = Clients.query.all()
    leader = Clients.query.filter_by(leader=True).all()
    return jsonify({
        'leader': [dict(c.to_dict(), became_leader_at=c.became_leader_at.strftime("%Y-%m-%d %H:%M:%S") if c.became_leader_at else None) for c in leader],
        'alive': [dict(c.to_dict(), last_connected=c.last_connected.strftime("%Y-%m-%d %H:%M:%S") if c.last_connected else None,
                        last_disconnected=c.last_disconnected.strftime("%Y-%m-%d %H:%M:%S") if c.last_disconnected else None) for c in clients]
    })

@healthapp.route('/sales_data')
@record_api_metrics('sales_data')
def sales_data():
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)

    sales = (
        db.session.query(
            # 5-minute buckets
            (func.date_trunc('hour', Order.timestamp) + \
             (func.floor(func.extract('minute', Order.timestamp) / 5) * 5).cast(Integer) * text("interval '1 minute'")).label('time'),
            func.count().label('count')
        )
        .filter(Order.status == 'Completed', Order.timestamp >= day_ago)
        .group_by('time')
        .order_by('time')
        .all()
    )

    labels = [row.time.strftime('%H:%M') for row in sales]
    counts = [row.count for row in sales]

    return jsonify({'labels': labels, 'counts': counts})

@healthapp.route("/activity_log")
@record_api_metrics('activity_log')
def get_activity_log():
    results = (
        db.session.query(Activity.activitytime, Activity.label)
        .order_by(Activity.activitytime.desc())
        .limit(10)
        .all()
    )
    activities = [
        {'timestamp': ts.strftime("%Y-%m-%d %H:%M:%S"), 'activity': act}
        for ts, act in results
    ]
    return jsonify(activities)

# --- Metrics API ---
@healthapp.route('/api/metrics')
def get_api_metrics(metrics_source=None):
    """Returns API usage metrics."""
    source = metrics_source if metrics_source is not None else api_metrics # Use provided source or global
    calculated_metrics = {}
    for endpoint, data in source.items(): # Use the determined source
        count = data['count']
        total_time = data['total_time']
        if count > 0:
            average_time = total_time / count
            calculated_metrics[endpoint] = {
                'count': count,
                'total_time': round(total_time, 4),
                'average_time': round(average_time, 4)
            }
        else:
             calculated_metrics[endpoint] = {
                'count': 0,
                'total_time': 0.0,
                'average_time': 0.0
            }

    # Restore usage statistics calculation
    if source: # Check if source is not empty
        total_calls = sum(data['count'] for data in source.values())
        most_called_item = max(source.items(), key=lambda item: item[1]['count'], default=None)
        most_called = most_called_item[0] if most_called_item else None
    else:
        total_calls = 0
        most_called = None

    calculated_metrics['usage'] = {
        'total_calls': total_calls,
        'most_called': most_called
    }

    return jsonify(calculated_metrics)

if __name__ == '__main__':
    app = create_healthapp()
    
    with app.app_context():
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

        db.create_all()
        health_host = os.environ.get('HOST', 'HEALTH_NODE_URL')
        port = int(os.environ.get('PORT', 'HEALTH_PORT'))
        socketio.run(app, debug=True, host=health_host, port=port)