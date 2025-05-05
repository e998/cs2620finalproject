from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
from dotenv import load_dotenv
import os
import sys
import threading
from sqlalchemy import exc as sqlalchemy_exc
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from shared.extensions import db, migrate

# Initialize extensions
login_manager = LoginManager()
load_dotenv()
socketio = SocketIO(cors_allowed_origins="*", message_queue=os.environ.get('REDIS_URL', 'redis://'))

# Flask-Login user loader setup
@login_manager.user_loader
def load_user(user_id):
    from shared.models import User 
    return db.session.get(User, int(user_id))

def create_app(test_config=None):
    app = Flask(__name__)
    # Load default configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'changeme')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Apply test configuration overrides if provided
    if test_config:
        app.config.update(test_config)

    # Initialize extensions AFTER config is finalized
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'
    socketio.init_app(app)

    from shared import models 

    # Register Blueprints
    from .routes import main
    app.register_blueprint(main)

    # Register Health Blueprint
    try:
        from health.healthapp import healthapp 
        app.register_blueprint(healthapp, url_prefix='/health') 
    except ImportError:
        print("Warning: Could not import or register health blueprint.")


    if not app.config.get('TESTING'):
        from shared.models import Clients
        from .routes import leader_election, retry_replications # Import background tasks

        try:
            with app.app_context():
                # Initialize leader state in the database
                LEADER_NODE = os.environ.get('LEADER_NODE_URL')
                if LEADER_NODE:
                    currleader = Clients.query.filter_by(client=LEADER_NODE).first()
                    if currleader:
                        if not currleader.leader:
                            currleader.leader = True # Ensure it's marked as leader
                            db.session.add(currleader)
                    else:
                        currleader = Clients(client=LEADER_NODE, leader=True)
                        db.session.add(currleader)
                    # Committing the potential change
                    db.session.commit()
                else:
                    print("Warning: LEADER_NODE_URL environment variable not set. Cannot initialize leader.")

            # Start background threads ONLY if leader init succeeded
            print("Starting background threads...")
            threading.Thread(target=leader_election, daemon=True).start()
            threading.Thread(target=retry_replications, daemon=True).start()
            print("Background threads started.")

        except sqlalchemy_exc.ProgrammingError as e:
            # Likely happens if tables don't exist yet (e.g., during flask db migrate/upgrade)
            with app.app_context():
                db.session.rollback() # Rollback any potential failed transaction
            print(f"Warning: Database error during leader initialization (likely missing tables?): {e}")
            print("Skipping leader initialization and background thread startup. Run 'flask db upgrade' and restart.")
        except Exception as e:
            # Catch other potential errors during init
            with app.app_context():
                db.session.rollback()
            print(f"Error during application initialization: {e}")

    return app
