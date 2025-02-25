from flask import Flask, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import docker
import threading
import time
import platform
import os
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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

logger.info(f"Using async_mode: {async_mode}")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode, logger=True, engineio_logger=True)

# Create Docker client based on the operating system
try:
    if platform.system() == 'Windows':
        # For Windows, use the named pipe
        docker_api = docker.DockerClient(base_url='npipe:////./pipe/docker_engine')
        logger.info("Connected to Docker using Windows named pipe")
    else:
        # For Unix-based systems, use the Unix socket
        docker_api = docker.DockerClient(base_url='unix://var/run/docker.sock')
        logger.info("Connected to Docker using Unix socket")
    
    # Test connection
    docker_api.ping()
    logger.info(f"Docker connection successful. API version: {docker_api.version()['ApiVersion']}")
except Exception as e:
    logger.error(f"Failed to connect to Docker: {e}")
    docker_api = None

container_stats = {}

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
                "system_info": system_info
            })
            logger.debug(f"Emitted stats for {len(container_stats)} containers")
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
        return jsonify([{
            "id": c.id, 
            "name": c.name, 
            "status": c.status
        } for c in containers])
    except Exception as e:
        logger.error(f"Error getting containers: {e}")
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
            "system_info": system_info
        })
        logger.info("Sent initial stats to new client connection")
    except Exception as e:
        logger.error(f"Error in handle_connect: {e}")
        emit("error", {"message": "Failed to get system information"})

# Start monitoring thread when app starts
try:
    thread = threading.Thread(target=fetch_container_stats, daemon=True)
    thread.name = "stats_thread"
    thread.start()
    logger.info("Monitoring thread started successfully")
except Exception as e:
    logger.error(f"Error starting monitoring thread: {e}")

if __name__ == "__main__":
    if async_mode == 'eventlet':
        try:
            import eventlet
            eventlet.monkey_patch()
            logger.info("Starting server with eventlet")
        except ImportError:
            logger.warning("Eventlet import failed")
    elif async_mode == 'gevent':
        try:
            from gevent import monkey
            monkey.patch_all()
            logger.info("Starting server with gevent")
        except ImportError:
            logger.warning("Gevent import failed")
    else:
        logger.info("Starting server with threading mode")
    
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, allow_unsafe_werkzeug=True)