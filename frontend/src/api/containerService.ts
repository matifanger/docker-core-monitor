// src/api/containerService.ts
import { env } from '$env/dynamic/public';
import type { Container } from '$lib/types';

const API_URL = env.PUBLIC_API_URL ?? 'http://localhost:5000';

/**
 * Fetch all containers
 */
export async function fetchContainers(): Promise<Container[]> {
    try {
        const res = await fetch(`${API_URL}/containers`);
        if (!res.ok) {
            console.error("Failed to fetch containers");
            return [];
        }
        
        return await res.json();
    } catch (e) {
        console.error("Error fetching containers", e);
        return [];
    }
}

/**
 * Fetch custom names for containers and groups
 */
export async function fetchCustomNames(): Promise<{ 
    containers: Record<string, string>, 
    groups: Record<string, string>,
    container_groups: Record<string, string>
}> {
    try {
        const res = await fetch(`${API_URL}/custom-names`);
        if (!res.ok) {
            console.error("Failed to fetch custom names");
            return { containers: {}, groups: {}, container_groups: {} };
        }
        
        return await res.json();
    } catch (e) {
        console.error("Failed to fetch custom names", e);
        return { containers: {}, groups: {}, container_groups: {} };
    }
}

/**
 * Update container name
 */
export async function updateContainerName(containerId: string, name: string): Promise<boolean> {
    try {
        const res = await fetch(`${API_URL}/custom-names/container/${containerId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name })
        });
        
        return res.ok;
    } catch (e) {
        console.error("Error updating container name", e);
        return false;
    }
}

/**
 * Update group name
 */
export async function updateGroupName(groupName: string, name: string): Promise<boolean> {
    try {
        const res = await fetch(`${API_URL}/custom-names/group/${groupName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name })
        });
        
        return res.ok;
    } catch (e) {
        console.error("Error updating group name", e);
        return false;
    }
}

/**
 * Reset container name to default
 */
export async function resetContainerName(containerId: string): Promise<boolean> {
    try {
        const res = await fetch(`${API_URL}/custom-names/container/${containerId}`, {
            method: 'DELETE'
        });
        
        return res.ok;
    } catch (e) {
        console.error("Error resetting container name", e);
        return false;
    }
}

/**
 * Reset group name to default
 */
export async function resetGroupName(groupName: string): Promise<boolean> {
    try {
        const res = await fetch(`${API_URL}/custom-names/group/${groupName}`, {
            method: 'DELETE'
        });
        
        return res.ok;
    } catch (e) {
        console.error("Error resetting group name", e);
        return false;
    }
}

/**
 * Update container group
 */
export async function updateContainerGroup(containerId: string, groupName: string): Promise<boolean> {
    try {
        const res = await fetch(`${API_URL}/container-group`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ containerId, groupName })
        });
        
        return res.ok;
    } catch (e) {
        console.error("Error updating container group", e);
        return false;
    }
}

/**
 * Reset container group to default
 */
export async function resetContainerGroup(containerId: string): Promise<boolean> {
    try {
        const res = await fetch(`${API_URL}/container-group/${containerId}`, {
            method: 'DELETE'
        });
        
        return res.ok;
    } catch (e) {
        console.error("Error resetting container group", e);
        return false;
    }
} 