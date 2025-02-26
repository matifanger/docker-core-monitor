from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import docker
import threading
import time
import platform
import os
import logging
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Configure logging - only errors and critical info
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Determine the best available async mode
async_mode = None
try:
    import eventlet
    async_mode = 'eventlet'
except ImportError:
    try:
        import gevent
        async_mode = 'gevent'
    except ImportError:
        async_mode = 'threading'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode, logger=False, engineio_logger=False)

# Create Docker client based on the operating system
try:
    if platform.system() == 'Windows':
        # For Windows, use the named pipe
        docker_api = docker.DockerClient(base_url='npipe:////./pipe/docker_engine')
    else:
        # For Unix-based systems, use the Unix socket
        docker_api = docker.DockerClient(base_url='unix://var/run/docker.sock')
    
    # Test connection
    docker_api.ping()
except Exception as e:
    logger.error(f"Failed to connect to Docker: {e}")
    docker_api = None

container_stats = {}

# Custom names storage
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
CUSTOM_NAMES_FILE = os.path.join(DATA_DIR, 'custom_names.json')

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
        cpu_count = stats["cpu_stats"]["online_cpus"]
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
        if system_delta > 0 and cpu_delta > 0:
            # Calcular el porcentaje real sin multiplicar por cpu_count
            return (cpu_delta / system_delta) * 100.0
        return 0.0
    except KeyError:
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
            memory_stats = stats.get("memory_stats", {})
            networks = stats.get("networks", {}).get("eth0", {"rx_bytes": 0, "tx_bytes": 0})
            blkio = stats.get("blkio_stats", {}).get("io_service_bytes_recursive", [])
            io_read = sum(b["value"] for b in blkio if b["op"] == "Read") or 0
            io_write = sum(b["value"] for b in blkio if b["op"] == "Write") or 0
            
            # Verificar si hay un límite de memoria real
            memory_limit = memory_stats.get("limit", 0)
            # Si el límite es igual al total del host, consideramos que no hay límite
            if memory_limit == docker_api.info()["MemTotal"]:
                memory_limit = 0
                
            return (container_id, {
                "name": container_name,
                "status": container_status,
                "cpu_percent": calculate_cpu_percent(stats),
                "cpu_count": stats["cpu_stats"]["online_cpus"],
                "cpu_limit": cpu_limit,
                "cpu_shares": cpu_shares,
                "memory_usage": memory_stats.get("usage", 0),
                "memory_limit": memory_limit,
                "network_rx": networks["rx_bytes"],
                "network_tx": networks["tx_bytes"],
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
    while True:
        try:
            if docker_api is None:
                logger.error("Docker API client is not initialized. Cannot fetch stats.")
                time.sleep(5)  # Wait a bit longer when there's an error
                continue
                
            containers = docker_api.containers.list(all=True)
            stats_data = {}
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(get_container_stats, c): c for c in containers}
                for future in futures:
                    container_id, stat = future.result()
                    # Apply custom container name if exists
                    if container_id in custom_names["containers"]:
                        stat["name"] = custom_names["containers"][container_id]
                    stats_data[container_id] = stat

            global container_stats
            container_stats = stats_data
            
            # Add system information as metadata
            try:
                system_info = {
                    "MemTotal": docker_api.info()["MemTotal"],
                    "NCPU": docker_api.info()["NCPU"]
                }
            except Exception as e:
                logger.error(f"Error getting system info: {e}")
                system_info = {
                    "MemTotal": 0,
                    "NCPU": 0
                }
            
            # Send the data in the format expected by the frontend
            socketio.emit("update_stats", {
                "containers": container_stats,
                "system_info": system_info,
                "custom_names": custom_names
            })
        except Exception as e:
            logger.error(f"Error in fetch_container_stats: {e}")
        time.sleep(2)

@app.route("/start", methods=["GET"])
def start_monitoring():
    thread = threading.Thread(target=fetch_container_stats, daemon=True)
    if not any(t.name == "stats_thread" for t in threading.enumerate()):
        thread.name = "stats_thread"
        thread.start()
    return jsonify({"message": "Monitoring started"})

@app.route("/containers", methods=["GET"])
def get_containers():
    try:
        if docker_api is None:
            logger.error("Docker API client is not initialized. Cannot get containers.")
            return jsonify({"error": "Docker API client is not initialized"}), 500
            
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
        if container_id in container_stats:
            container_stats[container_id]["name"] = data["name"]
            
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
        if docker_api is None:
            system_info = {
                "MemTotal": 0,
                "NCPU": 0
            }
        else:
            system_info = {
                "MemTotal": docker_api.info()["MemTotal"],
                "NCPU": docker_api.info()["NCPU"]
            }
        
        # Send the data in the format expected by the frontend
        emit("update_stats", {
            "containers": container_stats,
            "system_info": system_info,
            "custom_names": custom_names
        })
    except Exception as e:
        logger.error(f"Error in handle_connect: {e}")
        emit("error", {"message": "Failed to get system information"})

# Start monitoring thread when app starts
try:
    thread = threading.Thread(target=fetch_container_stats, daemon=True)
    thread.name = "stats_thread"
    thread.start()
except Exception as e:
    logger.error(f"Error starting monitoring thread: {e}")

if __name__ == "__main__":
    if async_mode == 'eventlet':
        try:
            import eventlet
            eventlet.monkey_patch()
        except ImportError:
            logger.warning("Eventlet import failed")
    elif async_mode == 'gevent':
        try:
            from gevent import monkey
            monkey.patch_all()
        except ImportError:
            logger.warning("Gevent import failed")
    
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)