import { writable, derived } from 'svelte/store';
import type { Container, Stats, NetworkHistory } from '$lib/types';
import { getNetworkChartUnit } from '$lib/utils/formatters';
import { updateGroupedContainers } from '$lib/utils/containerHelpers';
import { browser } from '$app/environment';

// Type for sort field
export type SortField = "memory" | "cpu" | "name" | "network_rx" | "network_tx" | "io_read" | "io_write" | "uptime" | "status";
export type SortDirection = "asc" | "desc";

// Initial state
export const containers = writable<Container[]>([]);
export const stats = writable<Record<string, Stats>>({});
export const customNames = writable<{ 
    containers: Record<string, string>, 
    groups: Record<string, string>,
    container_groups: Record<string, string>
}>({ 
    containers: {}, 
    groups: {},
    container_groups: {}
});
export const systemInfo = writable<{ MemTotal: number, NCPU: number }>({ MemTotal: 0, NCPU: 0 });
export const networkHistory = writable<NetworkHistory>({ rx: [], tx: [] });

// UI state
export const viewMode = writable<"groups" | "list">("groups");
export const sortField = writable<SortField>("memory");
export const sortDirection = writable<SortDirection>("desc");
export const isUserInteracting = writable<boolean>(false);
export const editingContainerId = writable<string | null>(null);
export const editingGroupName = writable<string | null>(null);
export const editingName = writable<string>('');
export const showSortOptions = writable<boolean>(false);

// Derived stores
export const groupedContainers = derived(
    [containers, customNames],
    ([$containers, $customNames]) => {
        return updateGroupedContainers($containers, $customNames.container_groups);
    }
);

export const sortedGroups = derived(
    [groupedContainers],
    ([$groupedContainers]) => {
        return Object.entries($groupedContainers || {}).sort((a, b) => {
            const aRunning = a[1].some(c => c.status === "running") ? 1 : 0;
            const bRunning = b[1].some(c => c.status === "running") ? 1 : 0;
            return bRunning - aRunning;
        });
    }
);

export const sortedContainers = derived(
    [containers, stats, sortField, sortDirection],
    ([$containers, $stats, $sortField, $sortDirection]) => {
        return ($containers || [])
            .map(c => ({ ...c, stats: $stats?.[c.id] || {} }))
            .sort((a, b) => {
                // Get values based on sort field
                let aValue, bValue;
                
                switch ($sortField) {
                    case "memory":
                        aValue = a.stats.memory_usage || 0;
                        bValue = b.stats.memory_usage || 0;
                        break;
                    case "cpu":
                        aValue = a.stats.cpu_percent || 0;
                        bValue = b.stats.cpu_percent || 0;
                        break;
                    case "name":
                        aValue = a.name.toLowerCase();
                        bValue = b.name.toLowerCase();
                        break;
                    case "network_rx":
                        aValue = a.stats.network_rx || 0;
                        bValue = b.stats.network_rx || 0;
                        break;
                    case "network_tx":
                        aValue = a.stats.network_tx || 0;
                        bValue = b.stats.network_tx || 0;
                        break;
                    case "io_read":
                        aValue = a.stats.io_read || 0;
                        bValue = b.stats.io_read || 0;
                        break;
                    case "io_write":
                        aValue = a.stats.io_write || 0;
                        bValue = b.stats.io_write || 0;
                        break;
                    case "uptime":
                        aValue = a.stats.uptime || 0;
                        bValue = b.stats.uptime || 0;
                        break;
                    case "status":
                        // Sort running containers first
                        aValue = a.status === "running" ? 1 : 0;
                        bValue = b.status === "running" ? 1 : 0;
                        break;
                    default:
                        aValue = a.stats.memory_usage || 0;
                        bValue = b.stats.memory_usage || 0;
                }
                
                // Apply sort direction
                if ($sortDirection === "asc") {
                    return aValue > bValue ? 1 : aValue < bValue ? -1 : 0;
                } else {
                    return aValue < bValue ? 1 : aValue > bValue ? -1 : 0;
                }
            });
    }
);

export const totalStats = derived(
    [stats, systemInfo],
    ([$stats, $systemInfo]) => {
        const statsValues = Object.values($stats || {});
        return {
            cpuPercent: statsValues.reduce((sum, stat) => sum + stat.cpu_percent, 0),
            cpuCount: statsValues.reduce((max, stat) => Math.max(max, stat.cpu_count || 0), 0),
            memoryUsage: statsValues.reduce((sum, stat) => sum + stat.memory_usage, 0),
            memoryLimit: $systemInfo?.MemTotal || 0,
            networkRx: statsValues.reduce((sum, stat) => sum + stat.network_rx, 0),
            networkTx: statsValues.reduce((sum, stat) => sum + stat.network_tx, 0),
            ioRead: statsValues.reduce((sum, stat) => sum + stat.io_read, 0),
            ioWrite: statsValues.reduce((sum, stat) => sum + stat.io_write, 0)
        };
    }
);

export const groupTotals = derived(
    [groupedContainers, stats],
    ([$groupedContainers, $stats]) => {
        return Object.keys($groupedContainers || {}).reduce((acc: Record<string, { 
            cpu: number, 
            cpuCount: number, 
            memory: number, 
            memoryLimit: number, 
            networkRx: number, 
            networkTx: number, 
            ioRead: number, 
            ioWrite: number 
        }>, groupName) => {
            const groupStats = ($groupedContainers[groupName] || []).map(c => 
                $stats?.[c.id] || { 
                    cpu_percent: 0, 
                    cpu_count: 0, 
                    memory_usage: 0, 
                    memory_limit: 0, 
                    network_rx: 0, 
                    network_tx: 0, 
                    io_read: 0, 
                    io_write: 0 
                }
            );
            
            acc[groupName] = {
                cpu: groupStats.reduce((sum, stat) => sum + stat.cpu_percent, 0),
                cpuCount: Math.max(...groupStats.map(stat => stat.cpu_count || 0)),
                memory: groupStats.reduce((sum, stat) => sum + stat.memory_usage, 0),
                memoryLimit: Math.max(...groupStats.map(stat => stat.memory_limit || 0)),
                networkRx: groupStats.reduce((sum, stat) => sum + stat.network_rx, 0),
                networkTx: groupStats.reduce((sum, stat) => sum + stat.network_tx, 0),
                ioRead: groupStats.reduce((sum, stat) => sum + stat.io_read, 0),
                ioWrite: groupStats.reduce((sum, stat) => sum + stat.io_write, 0)
            };
            return acc;
        }, {});
    }
);

export const chartData = derived(
    [networkHistory],
    ([$networkHistory]) => {
        const allValues = [...($networkHistory?.rx || []), ...($networkHistory?.tx || [])];
        const { divisor, unit } = getNetworkChartUnit(allValues);
        
        return {
            labels: Array.from({ length: 10 }, (_, i) => `T-${9 - i}`),
            datasets: [
                {
                    label: `RX (${unit})`,
                    data: ($networkHistory?.rx || []).map(v => v / divisor),
                    borderColor: '#00ffcc',
                    backgroundColor: 'rgba(0, 255, 204, 0.2)',
                    fill: true,
                    tension: 0.4,
                },
                {
                    label: `TX (${unit})`,
                    data: ($networkHistory?.tx || []).map(v => v / divisor),
                    borderColor: '#ff007a',
                    backgroundColor: 'rgba(255, 0, 122, 0.2)',
                    fill: true,
                    tension: 0.4,
                }
            ],
            unit,
            divisor
        };
    }
);

// Helper functions
export function updateNetworkHistory(statsData: Record<string, Stats>): void {
    networkHistory.update(history => {
        // Calculate network totals
        let totalRx = 0;
        let totalTx = 0;
        
        Object.values(statsData).forEach(stat => {
            totalRx += stat.network_rx || 0;
            totalTx += stat.network_tx || 0;
        });
        
        // Update history keeping the last 10 values
        return {
            rx: [...history.rx.slice(-9), totalRx],
            tx: [...history.tx.slice(-9), totalTx]
        };
    });
}

// Interaction state management
export function startEditing(): void {
    isUserInteracting.set(true);
}

export function stopEditing(): void {
    isUserInteracting.set(false);
}

export function startDragging(): void {
    isUserInteracting.set(true);
}

export function stopDragging(): void {
    isUserInteracting.set(false);
}

// Initialize the stores from localStorage if available
export function initializeStoresFromLocalStorage(): void {
    // Only run in browser environment
    if (!browser) return;
    
    try {
        const savedSortField = localStorage.getItem('dockerCoreSortField');
        const savedSortDirection = localStorage.getItem('dockerCoreSortDirection');
        const savedViewMode = localStorage.getItem('dockerCoreViewMode');
        
        if (savedSortField) {
            sortField.set(savedSortField as SortField);
        }
        
        if (savedSortDirection) {
            sortDirection.set(savedSortDirection as SortDirection);
        }
        
        if (savedViewMode) {
            viewMode.set(savedViewMode as "groups" | "list");
        }
    } catch (e) {
        console.error("Failed to load preferences from localStorage", e);
    }
}

// Save preferences to localStorage
export function savePreferences(field: string, value: string): void {
    // Only run in browser environment
    if (!browser) return;
    
    try {
        localStorage.setItem(`dockerCore${field}`, value);
    } catch (e) {
        console.error(`Failed to save ${field} preference`, e);
    }
} 