import os
import time
import json
import logging
import threading
import platform
import concurrent.futures
from datetime import datetime
from flask import Flask, jsonify, request, redirect, send_from_directory
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import docker
import requests

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

# Configure logging - only errors and critical info
logging.basicConfig(level=logging.ERROR, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

# Docker client connection settings
DOCKER_CLIENT_TIMEOUT = 30  # 30 seconds timeout for Docker API calls
DOCKER_MAX_POOL_SIZE = 100  # Maximum number of connections in the pool

# Initialize Docker API client
docker_api = None

def initialize_docker_client():
    """Initialize or reinitialize the Docker client with proper timeout settings"""
    global docker_api
    try:
        # Set timeout for Docker API requests
        if platform.system() == 'Windows':
            # For Windows, use the named pipe
            docker_api = docker.DockerClient(
                base_url='npipe:////./pipe/docker_engine',
                timeout=DOCKER_CLIENT_TIMEOUT,
                max_pool_size=DOCKER_MAX_POOL_SIZE
            )
        else:
            # For Unix-based systems, use the Unix socket
            docker_api = docker.DockerClient(
                base_url='unix://var/run/docker.sock',
                timeout=DOCKER_CLIENT_TIMEOUT,
                max_pool_size=DOCKER_MAX_POOL_SIZE
            )
        
        # Test connection
        docker_api.ping()
        logger.info("Successfully connected to Docker API")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Docker API client: {e}")
        docker_api = None
        return False

# Initial Docker client setup
initialize_docker_client()

container_stats = {}

# Global variables
stats = {}
custom_names = {"containers": {}, "groups": {}, "container_groups": {}}
monitoring_thread_running = False
last_docker_error_time = 0
docker_error_count = 0

# Constants
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CUSTOM_NAMES_FILE = os.path.join(DATA_DIR, "custom_names.json")

# Load custom names from file or initialize empty dict
def load_custom_names():
    try:
        # Create data directory if it doesn't exist
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            
        if os.path.exists(CUSTOM_NAMES_FILE):
            with open(CUSTOM_NAMES_FILE, 'r') as f:
                return json.load(f)
        return {"containers": {}, "groups": {}, "container_groups": {}}
    except Exception as e:
        logger.error(f"Error loading custom names: {e}")
        return {"containers": {}, "groups": {}, "container_groups": {}}

# Save custom names to file
def save_custom_names(custom_names):
    try:
        with open(CUSTOM_NAMES_FILE, 'w') as f:
            json.dump(custom_names, f)
    except Exception as e:
        logger.error(f"Error saving custom names: {e}")

# Initialize custom names
custom_names = load_custom_names()

def calculate_cpu_percent(stats):
    try:
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})
        
        # Check if we have the required fields
        if not cpu_stats or not precpu_stats:
            return 0.0
            
        cpu_total_usage = cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        precpu_total_usage = precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        
        # If we don't have valid usage data, return 0
        if not cpu_total_usage or not precpu_total_usage:
            return 0.0
            
        cpu_system_usage = cpu_stats.get("system_cpu_usage", 0)
        precpu_system_usage = precpu_stats.get("system_cpu_usage", 0)
        
        # If we don't have valid system usage data, return 0
        if not cpu_system_usage or not precpu_system_usage:
            return 0.0
            
        # Get number of CPUs
        cpu_count = cpu_stats.get("online_cpus", 0)
        
        if cpu_count == 0:
            # Fallback to number of CPUs in the system
            cpu_count = 1
        
        # Calculate CPU delta values
        cpu_delta = cpu_total_usage - precpu_total_usage
        system_delta = cpu_system_usage - precpu_system_usage
        
        if system_delta > 0 and cpu_delta > 0:
            # Calculate CPU usage percentage
            # The original formula multiplies by cpu_count which can lead to values over 100%
            # We'll divide by cpu_count instead to get per-core average
            cpu_percent = (cpu_delta / system_delta) * 100.0
            
            # Apply a sanity check to prevent unreasonably high values
            if cpu_percent > 100.0 * cpu_count:
                cpu_percent = 100.0 * cpu_count
                
            return round(cpu_percent, 2)
        else:
            return 0.0
    except Exception as e:
        logger.error(f"Error calculating CPU percent: {e}")
        return 0.0

def get_container_stats(container):
    try:
        # Get container details
        container_id = container.id
        container_name = container.name
        container_status = container.status
        
        # Parse StartedAt
        started_at_str = container.attrs["State"]["StartedAt"]
        # Format expected: '2025-02-24T03:26:18.76286698+00:00'
        # Truncate to microseconds (6 digits) and handle the offset
        started_at = datetime.strptime(started_at_str.split('.')[0] + '.' + started_at_str.split('.')[1][:6] + '+0000', '%Y-%m-%dT%H:%M:%S.%f%z')
        uptime = (time.time() - started_at.timestamp()) if container_status == "running" else 0
        
        # Obtener límites de CPU
        cpu_limit = None
        cpu_shares = None
        
        # Verificar si hay límites de CPU configurados
        host_config = container.attrs.get("HostConfig", {})
        if host_config.get("NanoCpus"):
            # NanoCpus está en billonésimas de CPU, convertir a número de CPUs
            cpu_limit = host_config.get("NanoCpus") / 1e9
        elif host_config.get("CpuPeriod") and host_config.get("CpuQuota"):
            # Otra forma de limitar CPUs
            cpu_limit = host_config.get("CpuQuota") / host_config.get("CpuPeriod")
        
        # CPU Shares (peso relativo)
        if host_config.get("CpuShares") and host_config.get("CpuShares") != 0 and host_config.get("CpuShares") != 1024:
            cpu_shares = host_config.get("CpuShares")
        
        # Obtener número de CPUs asignadas
        cpu_count = None
        if container.attrs.get("Config", {}).get("Cpuset"):
            cpuset = container.attrs.get("Config", {}).get("Cpuset")
            if cpuset:
                # Contar cuántos CPUs están asignados en el cpuset
                cpu_count = len([x for x in cpuset.split(',') if x])
        
        if container_status == "running":
            # Use a timeout for stats call to prevent hanging
            try:
                stats = container.stats(stream=False)
            except requests.exceptions.ReadTimeout:
                logger.warning(f"Timeout getting stats for container {container_name}")
                raise ValueError("Stats request timed out")
            
            # Check if stats is None or doesn't have required fields
            if not stats:
                logger.error(f"No stats available for container {container_name}")
                raise ValueError("No stats available")
                
            # Get memory stats with safe fallbacks
            memory_stats = stats.get("memory_stats", {})
            
            # Get network stats with safe fallbacks
            networks = stats.get("networks", {})
            network_stats = networks.get("eth0", {}) if networks else {}
            rx_bytes = network_stats.get("rx_bytes", 0)
            tx_bytes = network_stats.get("tx_bytes", 0)
            
            # Get block IO stats with safe fallbacks
            blkio_stats = stats.get("blkio_stats", {})
            io_service_bytes = blkio_stats.get("io_service_bytes_recursive", [])
            
            # Check if io_service_bytes is None before iterating
            if io_service_bytes is None:
                io_read = 0
                io_write = 0
            else:
                io_read = sum(b.get("value", 0) for b in io_service_bytes if b.get("op") == "Read")
                io_write = sum(b.get("value", 0) for b in io_service_bytes if b.get("op") == "Write")
            
            # Check for CPU stats
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            
            # Safe CPU calculation
            if "online_cpus" in cpu_stats:
                cpu_count = cpu_stats.get("online_cpus", 0)
            else:
                cpu_count = 0
                
            # Verificar si hay un límite de memoria real
            memory_limit = memory_stats.get("limit", 0)
            # Si el límite es igual al total del host, consideramos que no hay límite
            if docker_api and memory_limit == docker_api.info().get("MemTotal", 0):
                memory_limit = 0
                
            return (container_id, {
                "name": container_name,
                "status": container_status,
                "cpu_percent": calculate_cpu_percent(stats) if cpu_stats and precpu_stats else 0.0,
                "cpu_count": cpu_count,
                "cpu_limit": cpu_limit,
                "cpu_shares": cpu_shares,
                "memory_usage": memory_stats.get("usage", 0),
                "memory_limit": memory_limit,
                "network_rx": rx_bytes,
                "network_tx": tx_bytes,
                "io_read": io_read,
                "io_write": io_write,
                "uptime": uptime
            })
        else:
            return (container_id, {
                "name": container_name,
                "status": container_status,
                "cpu_percent": 0.0,
                "cpu_count": 0,
                "cpu_limit": cpu_limit,
                "cpu_shares": cpu_shares,
                "memory_usage": 0,
                "memory_limit": 0,
                "network_rx": 0,
                "network_tx": 0,
                "io_read": 0,
                "io_write": 0,
                "uptime": 0
            })
    except Exception as e:
        logger.error(f"Error fetching stats for {container_name}: {e}")
        return (container_id, {
            "name": container_name,
            "status": "error",
            "cpu_percent": 0.0,
            "cpu_count": 0,
            "cpu_limit": None,
            "cpu_shares": None,
            "memory_usage": 0,
            "memory_limit": 0,
            "network_rx": 0,
            "network_tx": 0,
            "io_read": 0,
            "io_write": 0,
            "uptime": 0
        })

def fetch_container_stats():
    global stats, docker_api, docker_error_count, last_docker_error_time
    try:
        if docker_api is None:
            # Try to reinitialize Docker client if it's None
            if not initialize_docker_client():
                logger.error("Docker API client is not initialized. Cannot fetch stats.")
                return {}
        
        # Check if we need to reconnect to Docker
        if docker_error_count > 5:
            current_time = time.time()
            # If we've had multiple errors and it's been at least 30 seconds since the last reconnection attempt
            if current_time - last_docker_error_time > 30:
                logger.warning("Too many Docker errors, attempting to reconnect...")
                initialize_docker_client()
                last_docker_error_time = current_time
                docker_error_count = 0
        
        try:
            containers = docker_api.containers.list(all=True)
            # Reset error count on successful call
            docker_error_count = 0
        except Exception as e:
            logger.error(f"Error listing containers: {e}")
            docker_error_count += 1
            return stats  # Return last known stats instead of empty dict
        
        # Get stats for each container in parallel with a smaller thread pool
        # to avoid overwhelming the system
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            container_stats = list(executor.map(get_container_stats, containers))
        
        # Convert to dictionary
        stats_dict = {}
        for container_id, container_stats in container_stats:
            if container_stats["status"] != "error":  # Skip containers with errors
                stats_dict[container_id] = container_stats
        
        # Apply custom names if they exist
        for container_id, container_stats in stats_dict.items():
            if container_id in custom_names["containers"]:
                container_stats["name"] = custom_names["containers"][container_id]
        
        stats = stats_dict
        return stats
    except Exception as e:
        logger.error(f"Error fetching container stats: {e}")
        docker_error_count += 1
        return stats  # Return last known stats instead of empty dict

@socketio.on("connect")
def handle_connect():
    try:
        # Send initial stats to new client
        current_stats = {}
        if docker_api is not None:
            current_stats = fetch_container_stats()
        
        # Get system info
        system_info = {"MemTotal": 0, "NCPU": 0}
        if docker_api is not None:
            try:
                system_info = {
                    "MemTotal": docker_api.info().get("MemTotal", 0),
                    "NCPU": docker_api.info().get("NCPU", 0)
                }
            except Exception as e:
                logger.error(f"Error getting system info: {e}")
                # Try to reconnect
                if initialize_docker_client():
                    system_info = {
                        "MemTotal": docker_api.info().get("MemTotal", 0),
                        "NCPU": docker_api.info().get("NCPU", 0)
                    }
        
        # Send initial data
        emit("update_stats", {
            "containers": current_stats,
            "system_info": system_info,
            "custom_names": custom_names
        })
        
        # Make sure monitoring thread is running - call start_monitoring_internal directly
        # instead of relying on the frontend to call the /start endpoint
        if docker_api is not None:
            # Call the internal function directly instead of the endpoint
            start_monitoring_internal()
    except Exception as e:
        logger.error(f"Error handling socket connection: {e}")
        emit("error", {"message": "Failed to get initial stats"})

def monitoring_thread():
    """Thread that continuously fetches container stats and emits them via Socket.IO"""
    global docker_api, monitoring_thread_running
    
    # Keep track of consecutive errors
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while monitoring_thread_running:
        try:
            # Check if Docker client needs to be reinitialized
            if docker_api is None:
                if not initialize_docker_client():
                    logger.error("Docker API client is not initialized. Cannot fetch stats.")
                    time.sleep(5)  # Wait a bit longer when there's an error
                    consecutive_errors += 1
                    continue
            
            # Fetch container stats
            stats_data = fetch_container_stats()
            
            # Reset consecutive errors counter on success
            consecutive_errors = 0
            
            # Add system information as metadata
            try:
                if docker_api:
                    system_info = {
                        "MemTotal": docker_api.info().get("MemTotal", 0),
                        "NCPU": docker_api.info().get("NCPU", 0)
                    }
                else:
                    system_info = {
                        "MemTotal": 0,
                        "NCPU": 0
                    }
            except Exception as e:
                logger.error(f"Error getting system info: {e}")
                consecutive_errors += 1
                
                # Try to reconnect to Docker
                if initialize_docker_client():
                    system_info = {
                        "MemTotal": docker_api.info().get("MemTotal", 0),
                        "NCPU": docker_api.info().get("NCPU", 0)
                    }
                else:
                    system_info = {
                        "MemTotal": 0,
                        "NCPU": 0
                    }
            
            # Send the data in the format expected by the frontend
            socketio.emit("update_stats", {
                "containers": stats_data,
                "system_info": system_info,
                "custom_names": custom_names
            })
            
            # Sleep for a bit before the next update
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"Error in monitoring thread: {e}")
            consecutive_errors += 1
            
            # If we have too many consecutive errors, try to reconnect to Docker
            if consecutive_errors >= max_consecutive_errors:
                logger.warning(f"Too many consecutive errors ({consecutive_errors}), attempting to reconnect to Docker...")
                initialize_docker_client()
                consecutive_errors = 0
                
            time.sleep(2)

# Internal function to start monitoring (not exposed as an endpoint)
def start_monitoring_internal():
    global monitoring_thread_running
    
    # Try to initialize Docker client if it's None
    if docker_api is None:
        if not initialize_docker_client():
            logger.error("Docker API client is not initialized. Cannot start monitoring.")
            return False
    
    if not monitoring_thread_running:
        monitoring_thread_running = True
        thread = threading.Thread(target=monitoring_thread)
        thread.daemon = True
        thread.start()
        logger.info("Monitoring thread started internally")
    
    return True

@app.route("/api/containers", methods=["GET"])
def get_containers_api():
    global docker_api, docker_error_count
    try:
        # Try to initialize Docker client if it's None
        if docker_api is None:
            if not initialize_docker_client():
                logger.error("Docker API client is not initialized. Cannot get containers.")
                return jsonify({"error": "Docker API client is not initialized. Please make sure Docker is running and accessible."}), 500
        
        try:
            containers = docker_api.containers.list(all=True)
            # Reset error count on successful call
            docker_error_count = 0
        except Exception as e:
            logger.error(f"Error listing containers: {e}")
            docker_error_count += 1
            # Try to reconnect
            if initialize_docker_client():
                containers = docker_api.containers.list(all=True)
            else:
                return jsonify({"error": "Failed to connect to Docker API"}), 500
        
        container_list = []
        
        for c in containers:
            container_data = {
                "id": c.id, 
                "name": c.name, 
                "status": c.status
            }
            
            # Apply custom container name if exists
            if c.id in custom_names["containers"]:
                container_data["name"] = custom_names["containers"][c.id]
                
            container_list.append(container_data)
            
        return jsonify(container_list)
    except Exception as e:
        logger.error(f"Error getting containers: {e}")
        return jsonify({"error": str(e)}), 500

# API endpoints for custom names
@app.route("/custom-names", methods=["GET"])
def get_custom_names():
    return jsonify(custom_names)

@app.route("/custom-names/container/<container_id>", methods=["POST"])
def update_container_name(container_id):
    try:
        data = request.json
        if not data or "name" not in data:
            return jsonify({"error": "Name is required"}), 400
            
        # Update container name
        custom_names["containers"][container_id] = data["name"]
        save_custom_names(custom_names)
        
        # Update stats with new name
        if container_id in stats:
            stats[container_id]["name"] = data["name"]
            
        return jsonify({"success": True, "message": "Container name updated"})
    except Exception as e:
        logger.error(f"Error updating container name: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/custom-names/group/<group_name>", methods=["POST"])
def update_group_name(group_name):
    try:
        data = request.json
        if not data or "name" not in data:
            return jsonify({"error": "Name is required"}), 400
            
        # Update group name
        custom_names["groups"][group_name] = data["name"]
        save_custom_names(custom_names)
        
        return jsonify({"success": True, "message": "Group name updated"})
    except Exception as e:
        logger.error(f"Error updating group name: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/custom-names/container/<container_id>", methods=["DELETE"])
def reset_container_name(container_id):
    try:
        if container_id in custom_names["containers"]:
            del custom_names["containers"][container_id]
            save_custom_names(custom_names)
            
        return jsonify({"success": True, "message": "Container name reset"})
    except Exception as e:
        logger.error(f"Error resetting container name: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/custom-names/group/<group_name>", methods=["DELETE"])
def reset_group_name(group_name):
    try:
        if group_name in custom_names["groups"]:
            del custom_names["groups"][group_name]
            save_custom_names(custom_names)
            
        return jsonify({"success": True, "message": "Group name reset"})
    except Exception as e:
        logger.error(f"Error resetting group name: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/container-group", methods=["POST"])
def update_container_group():
    try:
        data = request.json
        if not data or "containerId" not in data or "groupName" not in data:
            return jsonify({"error": "Container ID and group name are required"}), 400
            
        container_id = data["containerId"]
        group_name = data["groupName"]
        
        # Update container group
        custom_names["container_groups"][container_id] = group_name
        save_custom_names(custom_names)
        
        return jsonify({"success": True, "message": "Container group updated"})
    except Exception as e:
        logger.error(f"Error updating container group: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/container-group/<container_id>", methods=["DELETE"])
def reset_container_group(container_id):
    try:
        if container_id in custom_names["container_groups"]:
            del custom_names["container_groups"][container_id]
            save_custom_names(custom_names)
            
        return jsonify({"success": True, "message": "Container group reset"})
    except Exception as e:
        logger.error(f"Error resetting container group: {e}")
        return jsonify({"error": str(e)}), 500

# Health check endpoint
@app.route("/health", methods=["GET"])
def health_check():
    """Simple health check endpoint to verify the server is running"""
    return jsonify({"status": "ok", "docker_connected": docker_api is not None})

# Root route handler - proxy requests to the frontend
@app.route("/", methods=["GET"])
def root():
    return redirect("/containers")

# Frontend route for containers - this is the key fix
# This route will catch requests to /containers from the frontend
@app.route("/containers", methods=["GET"])
def containers_frontend():
    return get_containers_api()

# Favicon route handler
@app.route("/favicon.ico", methods=["GET"])
def favicon():
    return "", 204  # No content response

if __name__ == "__main__":
    if async_mode == 'eventlet':
        # The timeout parameter isn't supported in this version of eventlet
        # Use socket_timeout instead which is the correct parameter
        listener = eventlet.listen(('0.0.0.0', 5000))
        # Set socket timeout on the listener
        listener.settimeout(120)
        eventlet.wsgi.server(listener, app)
    elif async_mode == 'gevent':
        http_server = WSGIServer(('0.0.0.0', 5000), app)
        http_server.serve_forever()
    else:
        socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)