from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
import os

# Initialize extensions
csrf = CSRFProtect()
db = SQLAlchemy()
login_manager = LoginManager()
socketio = SocketIO(cors_allowed_origins="*", message_queue=os.environ.get('REDIS_URL', 'redis://'))

# Flask-Login user loader setup
from .models import User
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'changeme')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://cs262_final_user:6uYZnPbZVd3bczQgRyeZqv53uehhp2bL@dpg-d02kh56uk2gs73ejhfj0-a/cs262_final')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    csrf.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    socketio.init_app(app)

    from .routes import main
    app.register_blueprint(main)

    return app
