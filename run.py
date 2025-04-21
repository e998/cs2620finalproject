from dotenv import load_dotenv
import os
from app import create_app, db, socketio

load_dotenv()
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host=os.environ.get('HOST', '10.250.20.28'))