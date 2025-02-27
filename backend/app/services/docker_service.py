"""
Docker service module for interacting with the Docker API
"""

import platform
import logging
import docker
from app.config import config

logger = logging.getLogger(__name__)

# Docker client instance
docker_api = None
docker_error_count = 0
last_docker_error_time = 0

def initialize_docker_client():
    """Initialize or reinitialize the Docker client with proper timeout settings"""
    global docker_api
    try:
        # Set timeout for Docker API requests
        if platform.system() == 'Windows':
            # For Windows, use the named pipe
            docker_api = docker.DockerClient(
                base_url='npipe:////./pipe/docker_engine',
                timeout=config.DOCKER_CLIENT_TIMEOUT,
                max_pool_size=config.DOCKER_MAX_POOL_SIZE
            )
        else:
            # For Unix-based systems, use the Unix socket
            docker_api = docker.DockerClient(
                base_url='unix://var/run/docker.sock',
                timeout=config.DOCKER_CLIENT_TIMEOUT,
                max_pool_size=config.DOCKER_MAX_POOL_SIZE
            )
        
        # Test connection
        docker_api.ping()
        logger.info("Successfully connected to Docker API")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Docker API client: {e}")
        docker_api = None
        return False

def get_docker_client():
    """Get the Docker client instance, initializing it if necessary"""
    global docker_api
    if docker_api is None:
        initialize_docker_client()
    return docker_api

def get_system_info():
    """Get system information from Docker"""
    client = get_docker_client()
    if client is None:
        return {"MemTotal": 0, "NCPU": 0}
    
    try:
        info = client.info()
        return {
            "MemTotal": info.get("MemTotal", 0),
            "NCPU": info.get("NCPU", 0)
        }
    except Exception as e:
        logger.error(f"Error getting system info: {e}")
        # Try to reconnect
        if initialize_docker_client():
            info = docker_api.info()
            return {
                "MemTotal": info.get("MemTotal", 0),
                "NCPU": info.get("NCPU", 0)
            }
        return {"MemTotal": 0, "NCPU": 0}

def get_containers(all_containers=True):
    """Get list of containers from Docker"""
    client = get_docker_client()
    if client is None:
        return []
    
    global docker_error_count
    try:
        containers = client.containers.list(all=all_containers)
        # Reset error count on successful call
        docker_error_count = 0
        return containers
    except Exception as e:
        logger.error(f"Error listing containers: {e}")
        docker_error_count += 1
        # Try to reconnect
        if initialize_docker_client():
            return docker_api.containers.list(all=all_containers)
        return []

# Initialize Docker client on module import
initialize_docker_client() 