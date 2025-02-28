import type { Container } from '$lib/types';

/**
 * Get display name for a container
 */
export function getContainerDisplayName(container: Container): string {
    return container.name;
}

/**
 * Get display name for a group
 */
export function getGroupDisplayName(groupName: string, customGroupNames: Record<string, string>): string {
    return customGroupNames[groupName] || groupName;
}

/**
 * Get the default group for a container based on its name
 */
export function getDefaultGroup(container: Container | null): string {
    if (!container) return "Unknown";
    
    // Default group is the first part of the name before any dash or underscore
    return container.name.split(/[-_]/)[0] || container.name;
}

/**
 * Get the default group for a container by ID
 */
export function getDefaultGroupById(containerId: string, containers: Container[]): string {
    const container = containers.find(c => c.id === containerId);
    if (!container) return "Unknown";
    
    return getDefaultGroup(container);
}

/**
 * Get the current group for a container
 */
export function getContainerGroup(
    containerId: string, 
    containers: Container[], 
    customContainerGroups: Record<string, string>
): string {
    // First check if there's a custom group assignment
    if (customContainerGroups[containerId]) {
        return customContainerGroups[containerId];
    }
    
    // Otherwise use the default grouping based on name
    return getDefaultGroupById(containerId, containers);
}

/**
 * Update grouped containers based on current containers and custom groups
 */
export function updateGroupedContainers(
    containers: Container[], 
    customContainerGroups: Record<string, string>
): Record<string, Container[]> {
    // Ensure containers is defined
    if (!containers || containers.length === 0) {
        return {};
    }
    
    return containers.reduce((acc: Record<string, Container[]>, container) => {
        const groupName = getContainerGroup(container.id, containers, customContainerGroups);
        if (!acc[groupName]) {
            acc[groupName] = [];
        }
        acc[groupName].push(container);
        return acc;
    }, {});
} 