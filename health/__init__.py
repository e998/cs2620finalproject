from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from dotenv import load_dotenv
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.extensions import db

def create_healthapp():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'changeme')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://cs262_final_user:6uYZnPbZVd3bczQgRyeZqv53uehhp2bL@dpg-d02kh56uk2gs73ejhfj0-a.oregon-postgres.render.com/cs262_final')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    
    from .healthapp import healthapp
    app.register_blueprint(healthapp)

    return app