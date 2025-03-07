"""
API routes for the application
"""

from flask import jsonify, request, redirect
from app import app
from app.services import docker_service, stats_service

# API endpoints for containers
@app.route("/api/containers", methods=["GET"])
def get_containers_api():
    try:
        docker_client = docker_service.get_docker_client()
        if docker_client is None:
            return jsonify({"error": "Docker API client is not initialized. Please make sure Docker is running and accessible."}), 500
        
        containers = docker_service.get_containers(all_containers=True)
        
        container_list = []
        
        for c in containers:
            container_data = {
                "id": c.id, 
                "name": c.name,
                "docker_name": c.name,  # Add original Docker name
                "status": c.status
            }
            
            # Apply custom container name if exists, using Docker name as key
            if c.name in stats_service.custom_names["containers"]:
                container_data["name"] = stats_service.custom_names["containers"][c.name]
                
            container_list.append(container_data)
            
        return jsonify(container_list)
    except Exception as e:
        app.logger.error(f"Error getting containers: {e}")
        return jsonify({"error": str(e)}), 500

# API endpoints for custom names
@app.route("/custom-names", methods=["GET"])
def get_custom_names():
    return jsonify(stats_service.custom_names)

@app.route("/custom-names/container/<path:container_name>", methods=["POST"])
def update_container_name(container_name):
    try:
        data = request.json
        if not data or "name" not in data:
            return jsonify({"error": "Name is required"}), 400
            
        # Update container name
        stats_service.custom_names["containers"][container_name] = data["name"]
        stats_service.save_custom_names(stats_service.custom_names)
        
        # Update stats with new name
        for container_id, container_stats in stats_service.stats.items():
            if container_stats.get("docker_name") == container_name:
                container_stats["name"] = data["name"]
            
        return jsonify({"success": True, "message": "Container name updated"})
    except Exception as e:
        app.logger.error(f"Error updating container name: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/custom-names/group/<group_name>", methods=["POST"])
def update_group_name(group_name):
    try:
        data = request.json
        if not data or "name" not in data:
            return jsonify({"error": "Name is required"}), 400
            
        # Update group name
        stats_service.custom_names["groups"][group_name] = data["name"]
        stats_service.save_custom_names(stats_service.custom_names)
        
        return jsonify({"success": True, "message": "Group name updated"})
    except Exception as e:
        app.logger.error(f"Error updating group name: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/custom-names/container/<path:container_name>", methods=["DELETE"])
def reset_container_name(container_name):
    try:
        if container_name in stats_service.custom_names["containers"]:
            del stats_service.custom_names["containers"][container_name]
            stats_service.save_custom_names(stats_service.custom_names)
            
        return jsonify({"success": True, "message": "Container name reset"})
    except Exception as e:
        app.logger.error(f"Error resetting container name: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/custom-names/group/<group_name>", methods=["DELETE"])
def reset_group_name(group_name):
    try:
        if group_name in stats_service.custom_names["groups"]:
            del stats_service.custom_names["groups"][group_name]
            stats_service.save_custom_names(stats_service.custom_names)
            
        return jsonify({"success": True, "message": "Group name reset"})
    except Exception as e:
        app.logger.error(f"Error resetting group name: {e}")
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
        stats_service.custom_names["container_groups"][container_id] = group_name
        stats_service.save_custom_names(stats_service.custom_names)
        
        return jsonify({"success": True, "message": "Container group updated"})
    except Exception as e:
        app.logger.error(f"Error updating container group: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/container-group/<container_id>", methods=["DELETE"])
def reset_container_group(container_id):
    try:
        if container_id in stats_service.custom_names["container_groups"]:
            del stats_service.custom_names["container_groups"][container_id]
            stats_service.save_custom_names(stats_service.custom_names)
            
        return jsonify({"success": True, "message": "Container group reset"})
    except Exception as e:
        app.logger.error(f"Error resetting container group: {e}")
        return jsonify({"error": str(e)}), 500

# Health check endpoint
@app.route("/health", methods=["GET"])
def health_check():
    """Simple health check endpoint to verify the server is running"""
    return jsonify({"status": "ok", "docker_connected": docker_service.docker_api is not None})

# Root route handler - proxy requests to the frontend
@app.route("/", methods=["GET"])
def root():
    return redirect("/containers")

# Frontend route for containers
@app.route("/containers", methods=["GET"])
def containers_frontend():
    return get_containers_api()