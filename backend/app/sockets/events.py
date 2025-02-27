"""
Socket.IO events for real-time communication
"""

import threading
import time
import logging
from flask_socketio import emit
from app import socketio
from app.services import docker_service, stats_service

logger = logging.getLogger(__name__)
monitoring_thread = None
monitoring_thread_running = False

def start_monitoring_internal():
    """Start the monitoring thread if it's not already running"""
    global monitoring_thread, monitoring_thread_running
    
    if monitoring_thread_running:
        return {"status": "already_running"}
    
    monitoring_thread_running = True
    
    def monitor_containers():
        """Background thread that monitors container stats and emits updates"""
        while monitoring_thread_running:
            try:
                # Fetch container stats
                current_stats = stats_service.fetch_container_stats()
                
                # Get system info
                system_info = docker_service.get_system_info()
                
                # Emit update to all connected clients
                socketio.emit("update_stats", {
                    "containers": current_stats,
                    "system_info": system_info,
                    "custom_names": stats_service.custom_names
                })
                
                # Sleep for a short interval
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error in monitoring thread: {e}")
                time.sleep(5)  # Sleep longer on error
    
    # Start the monitoring thread
    monitoring_thread = threading.Thread(target=monitor_containers)
    monitoring_thread.daemon = True
    monitoring_thread.start()
    
    return {"status": "started"}

def stop_monitoring_internal():
    """Stop the monitoring thread"""
    global monitoring_thread_running
    monitoring_thread_running = False
    return {"status": "stopped"}

@socketio.on("connect")
def handle_connect():
    """Handle client connection"""
    try:
        logger.info("Client connected")
        # Send initial stats to new client
        current_stats = {}
        logger.info("Fetching container stats")
        current_stats = stats_service.fetch_container_stats()
        
        logger.info("Fetching system info")
        # Get system info
        system_info = docker_service.get_system_info()

        logger.info("Sending initial data")
        # Send initial data
        emit("update_stats", {
            "containers": current_stats,
            "system_info": system_info,
            "custom_names": stats_service.custom_names
        })
        
        # Make sure monitoring thread is running
        start_monitoring_internal()
    except Exception as e:
        logger.error(f"Error handling socket connection: {e}")
        emit("error", {"message": "Failed to get initial stats"})

@socketio.on("request_stats")
def handle_request_stats():
    """Handle explicit request for stats from client"""
    try:
        # Fetch current stats
        current_stats = stats_service.fetch_container_stats()
        
        # Get system info
        system_info = docker_service.get_system_info()
        
        # Send data only to the requesting client
        emit("update_stats", {
            "containers": current_stats,
            "system_info": system_info,
            "custom_names": stats_service.custom_names
        })
        
        logger.info("Sent stats in response to explicit request")
    except Exception as e:
        logger.error(f"Error handling stats request: {e}")
        emit("error", {"message": "Failed to get stats on request"})

@socketio.on("start_monitoring")
def handle_start_monitoring():
    """Handle request to start monitoring"""
    result = start_monitoring_internal()
    emit("monitoring_status", result)

@socketio.on("stop_monitoring")
def handle_stop_monitoring():
    """Handle request to stop monitoring"""
    result = stop_monitoring_internal()
    emit("monitoring_status", result)

@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection"""
    logger.info("Client disconnected") 