import os
import time
import json
import logging
import threading
import platform
import concurrent.futures
from datetime import datetime
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import docker

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
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode, logger=False, engineio_logger=False)

# Initialize Docker API client
docker_api = None
try:
    if platform.system() == 'Windows':
        # For Windows, use the named pipe
        docker_api = docker.DockerClient(base_url='npipe:////./pipe/docker_engine')
    else:
        # For Unix-based systems, use the Unix socket
        docker_api = docker.DockerClient(base_url='unix://var/run/docker.sock')
    
    # Test connection
    docker_api.ping()
    logger.info("Successfully connected to Docker API")
except Exception as e:
    logger.error(f"Failed to initialize Docker API client: {e}")
    docker_api = None

container_stats = {}

# Global variables
stats = {}
custom_names = {"containers": {}, "groups": {}, "container_groups": {}}
monitoring_thread_running = False

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
            cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0
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
            stats = container.stats(stream=False)
            
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
    global stats
    try:
        if docker_api is None:
            logger.error("Docker API client is not initialized. Cannot fetch stats.")
            return {}
            
        containers = docker_api.containers.list(all=True)
        
        # Get stats for each container in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
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
        return {}

@app.route("/start", methods=["GET"])
def start_monitoring():
    global monitoring_thread_running
    
    if docker_api is None:
        return jsonify({"status": "error", "message": "Docker API client is not initialized"}), 500
        
    if not monitoring_thread_running:
        monitoring_thread_running = True
        thread = threading.Thread(target=monitoring_thread)
        thread.daemon = True
        thread.start()
        
    return jsonify({"status": "ok"})

@app.route("/containers", methods=["GET"])
def get_containers():
    try:
        if docker_api is None:
            logger.error("Docker API client is not initialized. Cannot get containers.")
            return jsonify({"error": "Docker API client is not initialized. Please make sure Docker is running and accessible."}), 500
            
        containers = docker_api.containers.list(all=True)
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
        
        # Send initial data
        emit("update_stats", {
            "containers": current_stats,
            "system_info": system_info,
            "custom_names": custom_names
        })
        
        # Make sure monitoring thread is running
        if docker_api is not None:
            start_monitoring()
    except Exception as e:
        logger.error(f"Error handling socket connection: {e}")
        emit("error", {"message": "Failed to get initial stats"})

def monitoring_thread():
    """Thread that continuously fetches container stats and emits them via Socket.IO"""
    while True:
        try:
            if docker_api is None:
                logger.error("Docker API client is not initialized. Cannot fetch stats.")
                time.sleep(5)  # Wait a bit longer when there's an error
                continue
                
            # Fetch container stats
            stats_data = fetch_container_stats()
            
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
            time.sleep(2)

# Start monitoring thread when app starts
try:
    if docker_api is not None:
        monitoring_thread_running = True
        thread = threading.Thread(target=monitoring_thread)
        thread.daemon = True
        thread.start()
        logger.info("Monitoring thread started")
    else:
        logger.warning("Docker API client is not initialized. Monitoring thread not started.")
except Exception as e:
    logger.error(f"Failed to start monitoring thread: {e}")

if __name__ == "__main__":
    if async_mode == 'eventlet':
        eventlet.wsgi.server(eventlet.listen(('0.0.0.0', 5000)), app)
    elif async_mode == 'gevent':
        http_server = WSGIServer(('0.0.0.0', 5000), app)
        http_server.serve_forever()
    else:
        socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)