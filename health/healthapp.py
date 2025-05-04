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
    return render_template("health.html")

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
@healthapp.route('/api_metrics')
def get_api_metrics():
    data = {}
    for endpoint, stats in api_metrics.items():
        avg_time = stats['total_time'] / stats['count'] if stats['count'] else 0.0
        data[endpoint] = {
            'count': stats['count'],
            'avg_time': avg_time
        }
    # Usage statistics: total calls, most called endpoint
    total_calls = sum(stats['count'] for stats in api_metrics.values())
    most_called = max(api_metrics.items(), key=lambda x: x[1]['count'])[0] if api_metrics else None
    data['usage'] = {
        'total_calls': total_calls,
        'most_called': most_called
    }
    return jsonify(data)

# (Removed duplicate Clients model definition. Use the one in shared/models.py)

if __name__ == '__main__':
    app = create_healthapp()
    
    with app.app_context():
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

        db.create_all()
        health_host = os.environ.get('HOST', 'HEALTH_NODE_URL')
        port = int(os.environ.get('PORT', 'HEALTH_PORT'))
        socketio.run(app, debug=True, host=health_host, port=port)