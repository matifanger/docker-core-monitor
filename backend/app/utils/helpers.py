"""
Helper utility functions
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

def ensure_directory_exists(directory_path):
    """Ensure that a directory exists, creating it if necessary"""
    if not os.path.exists(directory_path):
        try:
            os.makedirs(directory_path)
            return True
        except Exception as e:
            logger.error(f"Error creating directory {directory_path}: {e}")
            return False
    return True

def load_json_file(file_path, default_value=None):
    """Load JSON data from a file, returning a default value if the file doesn't exist or is invalid"""
    if default_value is None:
        default_value = {}
        
    if not os.path.exists(file_path):
        return default_value
        
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON file {file_path}: {e}")
        return default_value

def save_json_file(file_path, data):
    """Save JSON data to a file"""
    try:
        # Ensure the directory exists
        directory = os.path.dirname(file_path)
        ensure_directory_exists(directory)
        
        with open(file_path, 'w') as f:
            json.dump(data, f)
        return True
    except Exception as e:
        logger.error(f"Error saving JSON file {file_path}: {e}")
        return False 