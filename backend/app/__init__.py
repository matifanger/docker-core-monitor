"""
Docker Core Monitor - Backend Application
"""

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up async mode for SocketIO
try:
    import eventlet
    async_mode = 'eventlet'
except ImportError:
    try:
        import gevent
        from gevent.pywsgi import WSGIServer
        async_mode = 'gevent'
    except ImportError:
        async_mode = 'threading'

# Apply monkey patching if using eventlet or gevent
if async_mode == 'eventlet':
    eventlet.monkey_patch()
elif async_mode == 'gevent':
    from gevent import monkey
    monkey.patch_all()

# Create Flask app
app = Flask(__name__)
# Enable CORS for all routes and origins
CORS(app)

# Configure SocketIO with ping_timeout and ping_interval to prevent disconnections
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode=async_mode, 
    logger=False, 
    engineio_logger=False,
    ping_timeout=60,  # Increase ping timeout to 60s
    ping_interval=25  # Increase ping interval to 25s
)

# Constants
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
CUSTOM_NAMES_FILE = os.path.join(DATA_DIR, "custom_names.json")

# Create data directory if it doesn't exist
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# Import components after app is created to avoid circular imports
from app.config import config
from app.services import docker_service, stats_service
from app.api import routes
from app.sockets import events

def create_app():
    """Factory function to create and configure the Flask application"""
    return app 