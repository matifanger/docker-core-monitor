"""
Configuration settings for the application
"""

# Docker client connection settings
DOCKER_CLIENT_TIMEOUT = 30  # 30 seconds timeout for Docker API calls
DOCKER_MAX_POOL_SIZE = 100  # Maximum number of connections in the pool

# Performance tuning for container stats
MAX_WORKER_THREADS = 20  # Increase max worker threads for better parallelism
CACHE_TTL_RUNNING = 3  # Cache TTL for running containers (seconds)
CACHE_TTL_STOPPED = 60  # Cache TTL for stopped containers (seconds)
BATCH_SIZE = 10  # Process containers in batches of this size

# Update intervals
FULL_UPDATE_INTERVAL = 30  # Full update every 30 seconds 