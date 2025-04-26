from dotenv import load_dotenv
from app import create_app, db, socketio

import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

load_dotenv()
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        socketio.run(app, debug=True, host=os.environ.get('HOST', '10.250.244.76'), port=int(os.environ.get('PORT', 5001)))
        # socketio.run(app, debug=True, host=os.environ.get('HOST', '10.250.20.28'), port=int(os.environ.get('PORT', 5001)))