from flask import Blueprint, jsonify, render_template, redirect, url_for, flash, request, session, g
from datetime import datetime, timedelta
from sqlalchemy import func

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.models import Order, Clients, Activity

from dotenv import load_dotenv
from health import create_healthapp
from app import db, socketio

load_dotenv()

healthapp = Blueprint('healthapp', __name__)

@healthapp.route("/")
def index():
    return render_template("health.html")

@healthapp.route("/cluster_status")
def get_cluster_status():
    clients = Clients.query.all()
    leader = Clients.query.filter_by(leader=True).all()
    return jsonify({
        'leader': [c.to_dict() for c in leader],
        'alive': [c.to_dict() for c in clients]
    })

@healthapp.route('/sales_data')
def sales_data():
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)

    # sales = Order.query.filter_by(status='Completed').all()
    sales = (
        db.session.query(
            func.date_trunc('minute', Order.timestamp).label('time'),
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

if __name__ == '__main__':
    app = create_healthapp()
    
    with app.app_context():
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

        db.create_all()
        health_host = os.environ.get('HOST', 'HEALTH_NODE_URL')
        port = int(os.environ.get('PORT', 'HEALTH_PORT'))
        socketio.run(app, debug=True, host=health_host, port=port)