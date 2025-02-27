#!/usr/bin/env python
"""
Main entry point for the Docker Core Monitor application
"""

import time
import logging
from app import app, socketio, async_mode

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    if async_mode == 'eventlet':
        import eventlet
        
        # Create a wrapper function to handle socket timeouts gracefully
        def run_server_with_timeout_handling():
            while True:
                try:
                    # Create a new listener each time
                    listener = eventlet.listen(('0.0.0.0', 5000))
                    # Set a reasonable socket timeout
                    listener.settimeout(120)
                    logger.info("Starting eventlet server on port 5000")
                    # Run the server - if it times out, we'll catch the exception and restart
                    eventlet.wsgi.server(listener, app)
                except TimeoutError:
                    logger.info("Server socket timed out, restarting listener")
                    # Close the listener socket if it's still open
                    try:
                        listener.close()
                    except:
                        pass
                    # Small delay before restarting
                    eventlet.sleep(1)
                except Exception as e:
                    logger.error(f"Server error: {e}, restarting in 5 seconds")
                    # Close the listener socket if it's still open
                    try:
                        listener.close()
                    except:
                        pass
                    # Longer delay for other errors
                    eventlet.sleep(5)
        
        # Start the server in a new greenlet
        server_thread = eventlet.spawn(run_server_with_timeout_handling)
        # Wait for the server thread
        server_thread.wait()
    elif async_mode == 'gevent':
        from gevent.pywsgi import WSGIServer
        http_server = WSGIServer(('0.0.0.0', 5000), app)
        http_server.serve_forever()
    else:
        socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True) 