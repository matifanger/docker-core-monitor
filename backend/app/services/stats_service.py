"""
Stats service module for container statistics
"""

import time
import logging
import json
import os
import concurrent.futures
import requests
from datetime import datetime
from app.config import config
from app.services import docker_service
from app import CUSTOM_NAMES_FILE

logger = logging.getLogger(__name__)

# Global variables
stats = {}
custom_names = {"containers": {}, "groups": {}, "container_groups": {}}
container_cache = {}
last_full_update_time = 0
monitoring_thread_running = False

def load_custom_names():
    """Load custom names from file or initialize empty dict"""
    try:
        if os.path.exists(CUSTOM_NAMES_FILE):
            with open(CUSTOM_NAMES_FILE, 'r') as f:
                return json.load(f)
        return {"containers": {}, "groups": {}, "container_groups": {}}
    except Exception as e:
        logger.error(f"Error loading custom names: {e}")
        return {"containers": {}, "groups": {}, "container_groups": {}}

def save_custom_names(names):
    """Save custom names to file"""
    try:
        with open(CUSTOM_NAMES_FILE, 'w') as f:
            json.dump(names, f)
    except Exception as e:
        logger.error(f"Error saving custom names: {e}")

def calculate_cpu_percent(stats):
    """Calculate CPU usage percentage from container stats"""
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
    """Get statistics for a single container"""
    try:
        # Get container details
        container_id = container.id
        container_name = container.name
        container_status = container.status
        
        # Check cache for non-running containers or containers that were recently fetched
        current_time = time.time()
        if container_id in container_cache:
            cached_data = container_cache[container_id]
            cache_age = current_time - cached_data.get("last_update_time", 0)
            
            # Use cache if:
            # 1. Container is not running and cache is not too old
            if container_status != "running" and cache_age < config.CACHE_TTL_STOPPED:
                return (container_id, cached_data)
                
            # 2. Container is running but cache is fresh enough
            if container_status == "running" and cache_age < config.CACHE_TTL_RUNNING:
                return (container_id, cached_data)
        
        # Parse StartedAt - only if needed and not in cache
        uptime = 0
        if container_status == "running":
            if container_id in container_cache and "uptime" in container_cache[container_id]:
                # Just update the uptime based on the previous value and elapsed time
                last_update = container_cache[container_id].get("last_update_time", current_time)
                uptime = container_cache[container_id].get("uptime", 0) + (current_time - last_update)
            else:
                # Only parse StartedAt if we don't have uptime in cache
                started_at_str = container.attrs["State"]["StartedAt"]
                # Format expected: '2025-02-24T03:26:18.76286698+00:00'
                # Truncate to microseconds (6 digits) and handle the offset
                started_at = datetime.strptime(started_at_str.split('.')[0] + '.' + started_at_str.split('.')[1][:6] + '+0000', '%Y-%m-%dT%H:%M:%S.%f%z')
                uptime = (current_time - started_at.timestamp())
        
        # Get CPU limits - only if not in cache or during full update
        cpu_limit = None
        cpu_shares = None
        cpu_count = None
        
        # Try to get these values from cache first
        if container_id in container_cache:
            cached_data = container_cache[container_id]
            cpu_limit = cached_data.get("cpu_limit")
            cpu_shares = cached_data.get("cpu_shares")
            cpu_count = cached_data.get("cpu_count")
        
        # Only fetch these expensive attributes during full updates or for new containers
        is_full_update = current_time - last_full_update_time <= config.FULL_UPDATE_INTERVAL
        if (container_id not in container_cache or is_full_update) and container.attrs:
            # CPU limits
            host_config = container.attrs.get("HostConfig", {})
            if host_config.get("NanoCpus"):
                cpu_limit = host_config.get("NanoCpus") / 1e9
            elif host_config.get("CpuPeriod") and host_config.get("CpuQuota"):
                cpu_limit = host_config.get("CpuQuota") / host_config.get("CpuPeriod")
            
            # CPU Shares
            if host_config.get("CpuShares") and host_config.get("CpuShares") != 0 and host_config.get("CpuShares") != 1024:
                cpu_shares = host_config.get("CpuShares")
            
            # CPU Count
            if container.attrs.get("Config", {}).get("Cpuset"):
                cpuset = container.attrs.get("Config", {}).get("Cpuset")
                if cpuset:
                    cpu_count = len([x for x in cpuset.split(',') if x])
        
        if container_status == "running":
            # Use a timeout for stats call to prevent hanging
            try:
                stats = container.stats(stream=False)
            except requests.exceptions.ReadTimeout:
                logger.warning(f"Timeout getting stats for container {container_name}")
                # Use cached data if available
                if container_id in container_cache:
                    return (container_id, container_cache[container_id])
                raise ValueError("Stats request timed out")
            
            # Check if stats is None or doesn't have required fields
            if not stats:
                logger.error(f"No stats available for container {container_name}")
                # Use cached data if available
                if container_id in container_cache:
                    return (container_id, container_cache[container_id])
                raise ValueError("No stats available")
                
            # Get memory stats with safe fallbacks
            memory_stats = stats.get("memory_stats", {})
            
            # Get network stats with safe fallbacks - only process what we need
            networks = stats.get("networks", {})
            rx_bytes = 0
            tx_bytes = 0
            if networks:
                for net_name, net_data in networks.items():
                    rx_bytes += net_data.get("rx_bytes", 0)
                    tx_bytes += net_data.get("tx_bytes", 0)
            
            # Get block IO stats with safe fallbacks - optimize processing
            blkio_stats = stats.get("blkio_stats", {})
            io_service_bytes = blkio_stats.get("io_service_bytes_recursive", [])
            
            io_read = 0
            io_write = 0
            if io_service_bytes:
                for io_stat in io_service_bytes:
                    op = io_stat.get("op")
                    if op == "Read":
                        io_read += io_stat.get("value", 0)
                    elif op == "Write":
                        io_write += io_stat.get("value", 0)
            
            # Check for CPU stats
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            
            # Update CPU count if available in stats
            if "online_cpus" in cpu_stats:
                cpu_count = cpu_stats.get("online_cpus", 0)
                
            # Check for memory limit
            memory_limit = memory_stats.get("limit", 0)
            # If limit equals host total, consider it unlimited
            docker_client = docker_service.get_docker_client()
            if docker_client and memory_limit == docker_client.info().get("MemTotal", 0):
                memory_limit = 0
            
            # Create stats object
            container_stats = {
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
                "uptime": uptime,
                "last_update_time": current_time
            }
            
            # Update cache
            container_cache[container_id] = container_stats
            
            return (container_id, container_stats)
        else:
            # For non-running containers
            container_stats = {
                "name": container_name,
                "status": container_status,
                "cpu_percent": 0.0,
                "cpu_count": cpu_count,
                "cpu_limit": cpu_limit,
                "cpu_shares": cpu_shares,
                "memory_usage": 0,
                "memory_limit": 0,
                "network_rx": 0,
                "network_tx": 0,
                "io_read": 0,
                "io_write": 0,
                "uptime": 0,
                "last_update_time": current_time
            }
            
            # Update cache
            container_cache[container_id] = container_stats
            
            return (container_id, container_stats)
    except Exception as e:
        logger.error(f"Error fetching stats for {container_name}: {e}")
        # Use cached data if available
        if container_id in container_cache:
            return (container_id, container_cache[container_id])
            
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
            "uptime": 0,
            "last_update_time": current_time
        })

def process_container_batch(containers):
    """Process a batch of containers in parallel"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_WORKER_THREADS) as executor:
        return list(executor.map(get_container_stats, containers))

def fetch_container_stats():
    """Fetch statistics for all containers"""
    global stats, last_full_update_time
    try:
        docker_client = docker_service.get_docker_client()
        if docker_client is None:
            logger.error("Docker API client is not initialized. Cannot fetch stats.")
            return {}
        
        # Determine if it's time for a full update
        current_time = time.time()
        is_full_update = current_time - last_full_update_time > config.FULL_UPDATE_INTERVAL
        
        # Update timestamp for full updates
        if is_full_update:
            last_full_update_time = current_time
            logger.info("Performing full container stats update")
        
        # For partial updates, only get running containers
        # to reduce load on Docker API
        containers = docker_service.get_containers(all_containers=is_full_update)
        
        # Measure execution time for diagnostics
        start_time = time.time()
        
        # Process containers in batches to avoid overwhelming the Docker API
        all_container_stats = []
        for i in range(0, len(containers), config.BATCH_SIZE):
            batch = containers[i:i+config.BATCH_SIZE]
            batch_stats = process_container_batch(batch)
            all_container_stats.extend(batch_stats)
        
        # Measure fetch time for diagnostics
        fetch_time = time.time() - start_time
        if fetch_time > 1.0:  # Only log if it takes more than 1 second
            logger.info(f"Container stats fetch took {fetch_time:.2f} seconds for {len(containers)} containers")
        
        # For partial updates, combine with existing stats
        if not is_full_update:
            # Keep existing stats for non-running containers
            stats_dict = stats.copy()
            # Update only running containers
            for container_id, container_stats in all_container_stats:
                if container_stats["status"] != "error":
                    stats_dict[container_id] = container_stats
        else:
            # For full updates, rebuild the dictionary
            stats_dict = {}
            for container_id, container_stats in all_container_stats:
                if container_stats["status"] != "error":
                    stats_dict[container_id] = container_stats
        
        # Apply custom names if they exist
        for container_id, container_stats in stats_dict.items():
            if container_id in custom_names["containers"]:
                container_stats["name"] = custom_names["containers"][container_id]
        
        stats = stats_dict
        return stats
    except Exception as e:
        logger.error(f"Error fetching container stats: {e}")
        return stats  # Return last known stats

# Initialize custom names on module import
custom_names = load_custom_names() 