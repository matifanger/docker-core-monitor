<script lang="ts">
    import { onMount, onDestroy } from "svelte";
    import { io } from "socket.io-client";
    import type { Container, Stats, NetworkHistory } from '$lib/types';
    import { env } from '$env/dynamic/public';
    // Íconos de Material Design
    import IconCpu from '~icons/mdi/monitor';
    import IconMemory from '~icons/mdi/memory';
    import IconNetwork from '~icons/mdi/network';
    import IconHardDrive from '~icons/mdi/harddisk';
    import IconClock from '~icons/mdi/clock';
    import IconGrid from '~icons/mdi/grid';
    import IconList from '~icons/mdi/format-list-bulleted';
    import IconSort from '~icons/mdi/sort';
    import IconSortAsc from '~icons/mdi/sort-ascending';
    import IconSortDesc from '~icons/mdi/sort-descending';
    import IconName from '~icons/mdi/alphabetical';
    import IconEdit from '~icons/mdi/pencil';
    import IconSave from '~icons/mdi/content-save';
    import IconCancel from '~icons/mdi/close';
    import IconReset from '~icons/mdi/refresh';
    import IconDrag from '~icons/mdi/drag';
    // Gráfico
    import { Chart } from 'chart.js/auto';

    // Click outside directive
    function clickOutside(node: HTMLElement, callback: () => void) {
        function handleClick(event: MouseEvent) {
            if (node && !node.contains(event.target as Node) && !event.defaultPrevented) {
                callback();
            }
        }
        
        document.addEventListener('click', handleClick, true);
        
        return {
            destroy() {
                document.removeEventListener('click', handleClick, true);
            }
        };
    }

    // Drag and drop directive
    function draggable(node: HTMLElement, data: any) {
        let state = data;

        node.draggable = true;
        
        function handleDragStart(event: DragEvent) {
            if (!event.dataTransfer) return;
            
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', JSON.stringify(state));
            
            node.classList.add('dragging');
            
            // Set a ghost image
            const ghost = node.cloneNode(true) as HTMLElement;
            ghost.style.position = 'absolute';
            ghost.style.top = '-1000px';
            ghost.style.opacity = '0.5';
            document.body.appendChild(ghost);
            event.dataTransfer.setDragImage(ghost, 0, 0);
            
            setTimeout(() => {
                document.body.removeChild(ghost);
            }, 0);
        }
        
        function handleDragEnd() {
            node.classList.remove('dragging');
        }
        
        node.addEventListener('dragstart', handleDragStart);
        node.addEventListener('dragend', handleDragEnd);
        
        return {
            update(newState: any) {
                state = newState;
            },
            destroy() {
                node.removeEventListener('dragstart', handleDragStart);
                node.removeEventListener('dragend', handleDragEnd);
            }
        };
    }
    
    // Drop zone directive
    function dropZone(node: HTMLElement, options: { onDrop: (data: any) => void }) {
        function handleDragOver(event: DragEvent) {
            event.preventDefault();
            if (!event.dataTransfer) return;
            
            event.dataTransfer.dropEffect = 'move';
            node.classList.add('drop-target');
        }
        
        function handleDragEnter(event: DragEvent) {
            event.preventDefault();
            node.classList.add('drop-target');
        }
        
        function handleDragLeave() {
            node.classList.remove('drop-target');
        }
        
        function handleDrop(event: DragEvent) {
            event.preventDefault();
            node.classList.remove('drop-target');
            
            if (!event.dataTransfer) return;
            
            try {
                const data = JSON.parse(event.dataTransfer.getData('text/plain'));
                options.onDrop(data);
            } catch (e) {
                console.error('Error parsing drag data', e);
            }
        }
        
        node.addEventListener('dragover', handleDragOver);
        node.addEventListener('dragenter', handleDragEnter);
        node.addEventListener('dragleave', handleDragLeave);
        node.addEventListener('drop', handleDrop);
        
        return {
            destroy() {
                node.removeEventListener('dragover', handleDragOver);
                node.removeEventListener('dragenter', handleDragEnter);
                node.removeEventListener('dragleave', handleDragLeave);
                node.removeEventListener('drop', handleDrop);
            }
        };
    }

    const API_URL = env.PUBLIC_API_URL ?? 'http://localhost:5000';
    const SOCKET_URL = env.PUBLIC_SOCKET_URL ?? 'http://localhost:5000';
    const REFRESH_INTERVAL = parseInt(env.PUBLIC_REFRESH_INTERVAL ?? '10000');

    let containers: Container[] = [];
    let stats: Record<string, Stats> = {};
    let intervalId: number | undefined;
    let networkHistory: NetworkHistory = { rx: [], tx: [] };
    let viewMode: "groups" | "list" = "groups";
    let systemInfo: { MemTotal: number, NCPU: number } = { MemTotal: 0, NCPU: 0 };
    
    // Custom names
    let customNames: { 
        containers: Record<string, string>, 
        groups: Record<string, string>,
        container_groups: Record<string, string>
    } = { 
        containers: {}, 
        groups: {},
        container_groups: {}
    };
    
    // Editing state
    let editingContainerId: string | null = null;
    let editingGroupName: string | null = null;
    let editingName: string = '';
    
    // Drag state
    let isDragging = false;
    let draggedContainer: Container | null = null;
    
    // Sort options
    type SortField = "memory" | "cpu" | "name" | "network_rx" | "network_tx" | "io_read" | "io_write" | "uptime" | "status";
    type SortDirection = "asc" | "desc";
    
    let sortField: SortField = "memory";
    let sortDirection: SortDirection = "desc";
    let showSortOptions = false;

    const sortOptions: {field: SortField, label: string, icon: any}[] = [
        { field: "memory", label: "Memory Usage", icon: IconMemory },
        { field: "cpu", label: "CPU Usage", icon: IconCpu },
        { field: "name", label: "Name", icon: IconName },
        { field: "network_rx", label: "Network RX", icon: IconNetwork },
        { field: "network_tx", label: "Network TX", icon: IconNetwork },
        { field: "io_read", label: "I/O Read", icon: IconHardDrive },
        { field: "io_write", label: "I/O Write", icon: IconHardDrive },
        { field: "uptime", label: "Uptime", icon: IconClock },
        { field: "status", label: "Status", icon: IconClock }
    ];

    let networkChart: Chart;

    // Make groupedContainers a writable variable
    let groupedContainers: Record<string, Container[]> = {};

    // Add connection status variables
    let isConnected = false;
    let connectionError = false;
    let reconnectAttempts = 0;
    let maxReconnectAttempts = 5;
    let reconnectInterval: number | null = null;
    let errorMessage = "Connection error";
    let showDetailedError = false;

    async function fetchContainers() {
        const res = await fetch(`${API_URL}/containers`);
        containers = await res.json();
    }

    async function startMonitoring() {
        await fetch(`${API_URL}/start`);
    }
    
    async function fetchCustomNames() {
        try {
            const res = await fetch(`${API_URL}/custom-names`);
            customNames = await res.json();
        } catch (e) {
            console.error("Failed to fetch custom names", e);
        }
    }
    
    async function updateContainerName(containerId: string, name: string) {
        try {
            // Store original name for potential rollback
            const originalName = containers.find(c => c.id === containerId)?.name;
            
            // Update local state immediately
            customNames = {
                ...customNames,
                containers: {
                    ...customNames.containers,
                    [containerId]: name
                }
            };
            
            // Update container name in the UI immediately
            containers = containers.map(c => 
                c.id === containerId ? { ...c, name } : c
            );
            
            // Reset editing state
            editingContainerId = null;
            editingName = '';
            
            // Then update on the server
            const res = await fetch(`${API_URL}/custom-names/container/${containerId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ name })
            });
            
            if (!res.ok) {
                console.error("Failed to update container name");
                // Revert local state if server update fails
                if (originalName) {
                    customNames = {
                        ...customNames,
                        containers: {
                            ...customNames.containers
                        }
                    };
                    delete customNames.containers[containerId];
                    
                    // Revert container name in UI
                    containers = containers.map(c => 
                        c.id === containerId ? { ...c, name: originalName } : c
                    );
                }
            }
        } catch (e) {
            console.error("Error updating container name", e);
        }
    }
    
    async function updateGroupName(originalName: string, newName: string) {
        try {
            // Store previous name for potential rollback
            const previousName = customNames.groups[originalName];
            
            // Update local state immediately
            customNames = {
                ...customNames,
                groups: {
                    ...customNames.groups,
                    [originalName]: newName
                }
            };
            
            // Reset editing state
            editingGroupName = null;
            editingName = '';
            
            // Then update on the server
            const res = await fetch(`${API_URL}/custom-names/group/${originalName}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ name: newName })
            });
            
            if (!res.ok) {
                console.error("Failed to update group name");
                // Revert local state if server update fails
                if (previousName) {
                    customNames = {
                        ...customNames,
                        groups: {
                            ...customNames.groups,
                            [originalName]: previousName
                        }
                    };
                } else {
                    customNames = {
                        ...customNames,
                        groups: {
                            ...customNames.groups
                        }
                    };
                    delete customNames.groups[originalName];
                }
            }
        } catch (e) {
            console.error("Error updating group name", e);
        }
    }
    
    async function resetContainerName(containerId: string) {
        try {
            // Store the custom name for potential rollback
            const customName = customNames.containers[containerId];
            const originalName = containers.find(c => c.id === containerId)?.name;
            
            // Update local state immediately
            customNames = {
                ...customNames,
                containers: {
                    ...customNames.containers
                }
            };
            delete customNames.containers[containerId];
            
            // Update container name in UI immediately if we know the original name
            if (originalName) {
                containers = containers.map(c => 
                    c.id === containerId ? { ...c, name: originalName } : c
                );
            }
            
            // Then update on the server
            const res = await fetch(`${API_URL}/custom-names/container/${containerId}`, {
                method: 'DELETE'
            });
            
            if (!res.ok) {
                console.error("Failed to reset container name");
                // Revert local state if server update fails
                if (customName) {
                    customNames = {
                        ...customNames,
                        containers: {
                            ...customNames.containers,
                            [containerId]: customName
                        }
                    };
                    
                    // Revert container name in UI
                    containers = containers.map(c => 
                        c.id === containerId ? { ...c, name: customName } : c
                    );
                }
            }
        } catch (e) {
            console.error("Error resetting container name", e);
        }
    }
    
    async function resetGroupName(groupName: string) {
        try {
            // Store the custom name for potential rollback
            const customName = customNames.groups[groupName];
            
            // Update local state immediately
            customNames = {
                ...customNames,
                groups: {
                    ...customNames.groups
                }
            };
            delete customNames.groups[groupName];
            
            // Then update on the server
            const res = await fetch(`${API_URL}/custom-names/group/${groupName}`, {
                method: 'DELETE'
            });
            
            if (!res.ok) {
                console.error("Failed to reset group name");
                // Revert local state if server update fails
                if (customName) {
                    customNames = {
                        ...customNames,
                        groups: {
                            ...customNames.groups,
                            [groupName]: customName
                        }
                    };
                }
            }
        } catch (e) {
            console.error("Error resetting group name", e);
        }
    }
    
    async function updateContainerGroup(containerId: string, groupName: string) {
        try {
            const res = await fetch(`${API_URL}/container-group`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    containerId, 
                    groupName 
                })
            });
            
            if (!res.ok) {
                console.error("Failed to update container group");
                // Revert local state if server update fails
                customNames = {
                    ...customNames,
                    container_groups: {
                        ...customNames.container_groups
                    }
                };
                delete customNames.container_groups[containerId];
            }
        } catch (e) {
            console.error("Error updating container group", e);
            // Revert local state if server update fails
            customNames = {
                ...customNames,
                container_groups: {
                    ...customNames.container_groups
                }
            };
            delete customNames.container_groups[containerId];
        }
    }
    
    async function resetContainerGroup(containerId: string) {
        try {
            // Store the previous value in case we need to revert
            const previousGroup = customNames.container_groups[containerId];
            
            // Update local state immediately
            customNames = {
                ...customNames,
                container_groups: {
                    ...customNames.container_groups
                }
            };
            delete customNames.container_groups[containerId];
            
            // Manually update groupedContainers for immediate UI update
            const container = containers.find(c => c.id === containerId);
            if (container && groupedContainers && previousGroup) {
                // Get the new group (original group based on name)
                const originalGroup = container.name.split(/[-_]/)[0] || container.name;
                
                // Remove from current group
                if (groupedContainers[previousGroup]) {
                    groupedContainers[previousGroup] = groupedContainers[previousGroup].filter(c => c.id !== containerId);
                    // If group is empty, remove it
                    if (groupedContainers[previousGroup].length === 0) {
                        delete groupedContainers[previousGroup];
                    }
                }
                
                // Add to original group
                if (!groupedContainers[originalGroup]) {
                    groupedContainers[originalGroup] = [];
                }
                groupedContainers[originalGroup].push(container);
                
                // Force reactivity update
                groupedContainers = {...groupedContainers};
            }
            
            // Then update on the server
            const res = await fetch(`${API_URL}/container-group/${containerId}`, {
                method: 'DELETE'
            });
            
            if (!res.ok) {
                console.error("Failed to reset container group");
                // Revert local state if server update fails
                if (previousGroup) {
                    customNames = {
                        ...customNames,
                        container_groups: {
                            ...customNames.container_groups,
                            [containerId]: previousGroup
                        }
                    };
                    
                    // Revert groupedContainers changes
                    if (container && groupedContainers) {
                        const originalGroup = container.name.split(/[-_]/)[0] || container.name;
                        
                        // Remove from original group
                        if (groupedContainers[originalGroup]) {
                            groupedContainers[originalGroup] = groupedContainers[originalGroup].filter(c => c.id !== containerId);
                            if (groupedContainers[originalGroup].length === 0) {
                                delete groupedContainers[originalGroup];
                            }
                        }
                        
                        // Add back to previous group
                        if (!groupedContainers[previousGroup]) {
                            groupedContainers[previousGroup] = [];
                        }
                        groupedContainers[previousGroup].push(container);
                        
                        // Force reactivity update
                        groupedContainers = {...groupedContainers};
                    }
                }
            }
        } catch (e) {
            console.error("Error resetting container group", e);
        }
    }
    
    function handleContainerDrop(groupName: string, containerData: { id: string, name: string }) {
        const currentGroup = getContainerGroup(containerData.id);
        if (currentGroup === groupName) {
            return; // Already in this group
        }
        
        // Update local state immediately
        customNames = {
            ...customNames,
            container_groups: {
                ...customNames.container_groups,
                [containerData.id]: groupName
            }
        };
        
        // Then update on the server
        updateContainerGroup(containerData.id, groupName);
        
        // Fetch containers immediately to update the UI
        fetchContainers();
        
        // And fetch again after a short delay to ensure we have the latest data
        setTimeout(fetchContainers, 500);
    }
    
    function startEditingContainer(containerId: string, currentName: string) {
        editingContainerId = containerId;
        editingName = currentName;
        // Close any open group editing
        editingGroupName = null;
    }
    
    function startEditingGroup(groupName: string, displayName: string) {
        editingGroupName = groupName;
        editingName = displayName;
        // Close any open container editing
        editingContainerId = null;
    }
    
    function cancelEditing() {
        editingContainerId = null;
        editingGroupName = null;
        editingName = '';
    }
    
    function setSortOption(field: SortField) {
        if (sortField === field) {
            // Toggle direction if same field
            sortDirection = sortDirection === "asc" ? "desc" : "asc";
        } else {
            sortField = field;
            // Default directions based on field type
            if (field === "name" || field === "status") {
                sortDirection = "asc";
            } else {
                sortDirection = "desc";
            }
        }
        
        // Save to localStorage
        try {
            localStorage.setItem("dockerCoreSort", JSON.stringify({ field: sortField, direction: sortDirection }));
        } catch (e) {
            console.error("Failed to save sort preferences", e);
        }
        
        // Close dropdown with a small delay to avoid flickering
        setTimeout(() => {
            showSortOptions = false;
        }, 100);
    }

    onMount(() => {
        fetchContainers();
        fetchCustomNames();
        startMonitoring();
        
        // Load sort preferences from localStorage
        try {
            const savedSort = localStorage.getItem("dockerCoreSort");
            if (savedSort) {
                const { field, direction } = JSON.parse(savedSort);
                sortField = field;
                sortDirection = direction;
            }
        } catch (e) {
            console.error("Failed to load sort preferences", e);
        }
        
        // Load view mode from localStorage
        try {
            const savedViewMode = localStorage.getItem("dockerCoreViewMode");
            if (savedViewMode) {
                viewMode = savedViewMode as "groups" | "list";
            }
        } catch (e) {
            console.error("Failed to load view mode", e);
        }

        // Add document click handler to close dropdown
        const handleDocumentClick = (e: MouseEvent) => {
            const sortButton = document.querySelector('.sort-button');
            const sortDropdown = document.querySelector('.sort-dropdown');
            
            if (showSortOptions && sortButton && sortDropdown) {
                if (!sortButton.contains(e.target as Node) && !sortDropdown.contains(e.target as Node)) {
                    showSortOptions = false;
                }
            }
        };
        
        document.addEventListener('click', handleDocumentClick);

        const canvas = document.getElementById('networkChart') as HTMLCanvasElement;
        networkChart = new Chart(canvas, {
            type: 'line',
            data: {
                labels: [],
                datasets: []
            }
        });

        const socket = io(SOCKET_URL, {
            reconnection: true,
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000
        });
        
        socket.on("connect", () => {
            console.log("Connected to WebSocket");
            isConnected = true;
            connectionError = false;
            errorMessage = "";
            reconnectAttempts = 0;
            
            // Clear any existing reconnect interval
            if (reconnectInterval) {
                clearInterval(reconnectInterval);
                reconnectInterval = null;
            }
        });
        
        socket.on("connect_error", (error) => {
            console.error("Socket connection error:", error);
            connectionError = true;
            isConnected = false;
            errorMessage = `Connection error: ${error.message || "Failed to connect to server"}`;
            
            // If we're not already trying to reconnect, start trying
            if (!reconnectInterval && reconnectAttempts < maxReconnectAttempts) {
                reconnectInterval = setInterval(() => {
                    reconnectAttempts++;
                    console.log(`Reconnect attempt ${reconnectAttempts}/${maxReconnectAttempts}`);
                    
                    if (reconnectAttempts >= maxReconnectAttempts) {
                        if (reconnectInterval) {
                            clearInterval(reconnectInterval);
                            reconnectInterval = null;
                        }
                        errorMessage = "Could not connect to server. Please check if Docker is running and accessible.";
                    } else {
                        // Try to reconnect
                        socket.connect();
                    }
                }, 5000) as unknown as number;
            }
        });
        
        socket.on("disconnect", (reason) => {
            console.log("Disconnected from WebSocket:", reason);
            isConnected = false;
            
            // If the disconnection wasn't initiated by the client, try to reconnect
            if (reason !== "io client disconnect") {
                connectionError = true;
                errorMessage = `Disconnected: ${reason}`;
                
                // If we're not already trying to reconnect, start trying
                if (!reconnectInterval && reconnectAttempts < maxReconnectAttempts) {
                    reconnectInterval = setInterval(() => {
                        reconnectAttempts++;
                        console.log(`Reconnect attempt ${reconnectAttempts}/${maxReconnectAttempts}`);
                        
                        if (reconnectAttempts >= maxReconnectAttempts) {
                            if (reconnectInterval) {
                                clearInterval(reconnectInterval);
                                reconnectInterval = null;
                            }
                            errorMessage = "Could not reconnect to server. Please check if Docker is running and accessible.";
                        } else {
                            // Try to reconnect
                            socket.connect();
                        }
                    }, 5000) as unknown as number;
                }
            }
        });
        
        socket.on("error", (error) => {
            console.error("Socket error:", error);
            errorMessage = error.message || "An error occurred with the server connection";
            connectionError = true;
        });
        
        socket.on("update_stats", (data: { 
            containers: Record<string, Stats>, 
            system_info: { MemTotal: number, NCPU: number },
            custom_names: { 
                containers: Record<string, string>, 
                groups: Record<string, string>,
                container_groups: Record<string, string>
            }
        }) => {
            stats = data.containers || {};
            systemInfo = data.system_info || { MemTotal: 0, NCPU: 0 };
            customNames = data.custom_names || { containers: {}, groups: {}, container_groups: {} };
            const totalRx = Object.values(stats).reduce((sum, stat) => sum + stat.network_rx, 0);
            const totalTx = Object.values(stats).reduce((sum, stat) => sum + stat.network_tx, 0);
            networkHistory.rx = [...networkHistory.rx.slice(-9), totalRx].slice(-10);
            networkHistory.tx = [...networkHistory.tx.slice(-9), totalTx].slice(-10);
            
            // Force update of groupedContainers to reflect any changes in container groups
            // This ensures the UI updates when container groups change from other clients
            groupedContainers = (containers || []).reduce((acc: Record<string, Container[]>, container) => {
                const groupName = getContainerGroup(container.id);
                acc[groupName] = acc[groupName] || [];
                acc[groupName].push(container);
                return acc;
            }, {});
        });

        intervalId = setInterval(fetchContainers, REFRESH_INTERVAL);

        return () => {
            socket.disconnect();
            if (intervalId) clearInterval(intervalId);
            if (networkChart) networkChart.destroy();
            if (reconnectInterval) clearInterval(reconnectInterval);
            document.removeEventListener('click', handleDocumentClick);
        };
    });

    onDestroy(() => {
        if (intervalId) clearInterval(intervalId);
        if (networkChart) networkChart.destroy();
    });

    function formatBytes(bytes: number): string {
        if (bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    }

    function formatTime(seconds: number): string {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        return `${h}h ${m}m ${s}s`;
    }

    // Normaliza el porcentaje de CPU para que no exceda el 100% por núcleo
    function normalizeCpuPercent(percent: number, cores?: number): number {
        // Si no hay información de cores, asumimos que es un solo núcleo
        const maxPercent = 100 * (cores || 1);
        // No limitamos el porcentaje, solo lo devolvemos tal cual
        return percent;
    }

    // Formatea la información de CPU para mostrar
    function formatCpuInfo(cpuPercent: number, cpuCount?: number | null, cpuLimit?: number | null): string {
        let result = `${cpuPercent.toFixed(2)}%`;
        if (cpuLimit) {
            result += ` / ${cpuLimit.toFixed(1)} CPUs`;
        } else if (cpuCount) {
            result += ` (${cpuCount} CPUs)`;
        }
        return result;
    }

    // Determina la unidad adecuada para los valores de red en el gráfico
    function getNetworkChartUnit(values: number[]): { divisor: number, unit: string } {
        const max = Math.max(...values, 1); // Evitar división por cero
        
        if (max >= 1e12) return { divisor: 1e12, unit: 'TB' };
        if (max >= 1e9) return { divisor: 1e9, unit: 'GB' };
        if (max >= 1e6) return { divisor: 1e6, unit: 'MB' };
        if (max >= 1e3) return { divisor: 1e3, unit: 'KB' };
        return { divisor: 1, unit: 'B' };
    }

    // Get display name for a container
    function getContainerDisplayName(container: Container): string {
        return container.name;
    }
    
    // Get display name for a group
    function getGroupDisplayName(groupName: string): string {
        return customNames.groups[groupName] || groupName;
    }
    
    // Get the group for a container (custom or original)
    function getContainerGroup(containerId: string): string {
        const container = containers.find(c => c.id === containerId);
        if (!container) return "";
        
        // If there's a custom group, use it
        if (customNames.container_groups && customNames.container_groups[containerId]) {
            return customNames.container_groups[containerId];
        }
        
        // Otherwise use the original group (first part of the name)
        return container.name.split(/[-_]/)[0] || container.name;
    }

    $: {
        // Update groupedContainers when containers or customNames change
        groupedContainers = (containers || []).reduce((acc: Record<string, Container[]>, container) => {
            // Use custom group if available, otherwise use the original group
            const groupName = getContainerGroup(container.id);
            
            acc[groupName] = acc[groupName] || [];
            acc[groupName].push(container);
            return acc;
        }, {});
    }

    $: sortedGroups = Object.entries(groupedContainers || {}).sort((a, b) => {
        const aRunning = a[1].some(c => c.status === "running") ? 1 : 0;
        const bRunning = b[1].some(c => c.status === "running") ? 1 : 0;
        return bRunning - aRunning; // Corregido el sort con valores numéricos
    });

    $: sortedContainers = (containers || [])
        .map(c => ({ ...c, stats: stats?.[c.id] || {} }))
        .sort((a, b) => {
            // Get values based on sort field
            let aValue, bValue;
            
            switch (sortField) {
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
            if (sortDirection === "asc") {
                return aValue > bValue ? 1 : aValue < bValue ? -1 : 0;
            } else {
                return aValue < bValue ? 1 : aValue > bValue ? -1 : 0;
            }
        });

    $: totalCpuPercent = Object.values(stats || {}).reduce((sum, stat) => sum + stat.cpu_percent, 0);
    $: totalCpuCount = Object.values(stats || {}).reduce((max, stat) => Math.max(max, stat.cpu_count || 0), 0);
    $: totalMemoryUsage = Object.values(stats || {}).reduce((sum, stat) => sum + stat.memory_usage, 0);
    $: totalMemoryLimit = systemInfo?.MemTotal || 0;
    $: totalNetworkRx = Object.values(stats || {}).reduce((sum, stat) => sum + stat.network_rx, 0);
    $: totalNetworkTx = Object.values(stats || {}).reduce((sum, stat) => sum + stat.network_tx, 0);
    $: totalIoRead = Object.values(stats || {}).reduce((sum, stat) => sum + stat.io_read, 0);
    $: totalIoWrite = Object.values(stats || {}).reduce((sum, stat) => sum + stat.io_write, 0);

    $: groupTotals = Object.keys(groupedContainers || {}).reduce((acc: Record<string, { cpu: number, cpuCount: number, memory: number, memoryLimit: number, networkRx: number, networkTx: number, ioRead: number, ioWrite: number }>, groupName) => {
        const groupStats = (groupedContainers[groupName] || []).map(c => stats?.[c.id] || { cpu_percent: 0, cpu_count: 0, memory_usage: 0, memory_limit: 0, network_rx: 0, network_tx: 0, io_read: 0, io_write: 0 });
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

    // Datos para el gráfico de red
    $: if (networkChart) {
        const allValues = [...(networkHistory?.rx || []), ...(networkHistory?.tx || [])];
        const { divisor, unit } = getNetworkChartUnit(allValues);
        
        networkChart.data = {
            labels: Array.from({ length: 10 }, (_, i) => `T-${9 - i}`),
            datasets: [
                {
                    label: `RX (${unit})`,
                    data: (networkHistory?.rx || []).map(v => v / divisor),
                    borderColor: '#00ffcc',
                    backgroundColor: 'rgba(0, 255, 204, 0.2)',
                    fill: true,
                    tension: 0.4,
                },
                {
                    label: `TX (${unit})`,
                    data: (networkHistory?.tx || []).map(v => v / divisor),
                    borderColor: '#ff007a',
                    backgroundColor: 'rgba(255, 0, 122, 0.2)',
                    fill: true,
                    tension: 0.4,
                }
            ]
        };
        networkChart.options = {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { 
                        color: '#fff',
                        callback: (value: any) => `${value} ${unit}`
                    },
                    grid: { color: 'rgba(255, 255, 255, 0.1)' }
                },
                x: {
                    ticks: { color: '#fff' },
                    grid: { color: 'rgba(255, 255, 255, 0.1)' }
                }
            },
            plugins: {
                legend: { labels: { color: '#fff' } },
                tooltip: {
                    callbacks: {
                        label: (context: any) => `${context.dataset.label}: ${formatBytes(context.raw * divisor)}`
                    }
                }
            }
        };
        networkChart.update('none');
    }
</script>

<main class="min-h-screen bg-gray-950 flex flex-col items-center p-4 md:p-8 overflow-hidden">
    <header class="w-full max-w-7xl mb-8">
        <div class="flex flex-col md:flex-row justify-between items-center gap-4">
            <h1 class="text-3xl md:text-5xl font-extrabold font-display text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-purple-500 tracking-tight">
                DOCKER CORE
            </h1>
            <button
                class="p-2 rounded-full bg-gray-800 text-cyan-400 hover:bg-cyan-600 transition-all cursor-pointer"
                on:click={() => {
                    viewMode = viewMode === 'groups' ? 'list' : 'groups';
                    // Save view mode to localStorage
                    try {
                        localStorage.setItem("dockerCoreViewMode", viewMode);
                    } catch (e) {
                        console.error("Failed to save view mode", e);
                    }
                }}
            >
                {#if viewMode === 'groups'}
                    <IconList class="w-6 h-6" />
                {:else}
                    <IconGrid class="w-6 h-6" />
                {/if}
            </button>
        </div>
        <div class="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6 text-gray-300 font-mono text-sm">
            <div class="space-y-4">
                <div>
                    <p><IconCpu class="inline w-4 h-4 mr-1" />CPU: <span class="text-cyan-400">{formatCpuInfo(totalCpuPercent, totalCpuCount, null)}</span></p>
                    <div class="w-full bg-gray-800 h-3 rounded-full mt-1 relative overflow-hidden">
                        <div class="bg-cyan-500 h-full rounded-full transition-all duration-500 animate-pulse" style="width: {Math.min(totalCpuPercent, 100)}%;"></div>
                        <div class="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent animate-flow"></div>
                    </div>
                </div>
                <div>
                    <p><IconMemory class="inline w-4 h-4 mr-1" />Memory: <span class="text-cyan-400">{formatBytes(totalMemoryUsage)}</span>
                    {#if totalMemoryLimit > 0 && totalMemoryLimit !== totalMemoryUsage}
                     / <span class="text-purple-400">{formatBytes(totalMemoryLimit)}</span>
                    {/if}
                    </p>
                    <div class="w-full bg-gray-800 h-3 rounded-full mt-1 relative overflow-hidden">
                        <div class="bg-cyan-500 h-full rounded-full transition-all duration-500 animate-pulse" style="width: {totalMemoryLimit > 0 ? ((totalMemoryUsage / totalMemoryLimit) * 100).toFixed(1) : 0}%;"></div>
                        <div class="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent animate-flow"></div>
                    </div>
                </div>
                <p><IconHardDrive class="inline w-4 h-4 mr-1" />I/O Read: <span class="text-cyan-400">{formatBytes(totalIoRead)}</span></p>
                <p><IconHardDrive class="inline w-4 h-4 mr-1" />I/O Write: <span class="text-cyan-400">{formatBytes(totalIoWrite)}</span></p>
            </div>
            <div class="space-y-4">
                <p class="text-cyan-400"><IconNetwork class="inline w-4 h-4 mr-1" />Network Flow</p>
                <div class="w-full h-32">
                    <canvas id="networkChart"></canvas>
                </div>
                <p>RX: <span class="text-cyan-400">{formatBytes(totalNetworkRx)}</span> | TX: <span class="text-pink-500">{formatBytes(totalNetworkTx)}</span></p>
            </div>
        </div>
    </header>

    {#if containers.length === 0}
        <div class="text-gray-500 text-xl font-mono animate-pulse">
            > No systems online...
        </div>
    {:else if viewMode === "groups"}
        <div class="w-full max-w-7xl space-y-8">
            {#each sortedGroups as [groupName, groupContainers]}
                <section class="space-y-4">
                    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2"
                         use:dropZone={{ onDrop: (data) => handleContainerDrop(groupName, data) }}>
                        <div class="flex items-center gap-2">
                            {#if editingGroupName === groupName}
                                <div class="flex items-center gap-2">
                                    <input 
                                        type="text" 
                                        bind:value={editingName} 
                                        class="bg-gray-800 text-white px-2 py-1 rounded border border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 min-w-[200px]"
                                        placeholder="Enter group name"
                                    />
                                    <button 
                                        class="text-green-400 hover:text-green-300 transition-colors"
                                        on:click={() => updateGroupName(groupName, editingName)}
                                        title="Save"
                                    >
                                        <IconSave class="w-5 h-5" />
                                    </button>
                                    <button 
                                        class="text-red-400 hover:text-red-300 transition-colors"
                                        on:click={cancelEditing}
                                        title="Cancel"
                                    >
                                        <IconCancel class="w-5 h-5" />
                                    </button>
                                </div>
                            {:else}
                                <h2 class="text-2xl md:text-3xl font-display text-cyan-400 uppercase tracking-wider flex items-center gap-2">
                                    {getGroupDisplayName(groupName)}
                                    <button 
                                        class="text-gray-400 hover:text-cyan-300 transition-colors"
                                        on:click={() => startEditingGroup(groupName, getGroupDisplayName(groupName))}
                                        title="Edit group name"
                                    >
                                        <IconEdit class="w-5 h-5" />
                                    </button>
                                    {#if customNames.groups[groupName]}
                                        <button 
                                            class="text-gray-400 hover:text-red-300 transition-colors"
                                            on:click={() => resetGroupName(groupName)}
                                            title="Reset to original name"
                                        >
                                            <IconReset class="w-5 h-5" />
                                        </button>
                                    {/if}
                                </h2>
                            {/if}
                        </div>
                        <div class="hidden md:flex space-x-4 text-sm text-gray-300 font-mono">
                            <span>CPU: <span class="text-cyan-400">{formatCpuInfo(groupTotals[groupName]?.cpu, groupTotals[groupName]?.cpuCount, null)}</span></span>
                            <span>MEM: <span class="text-cyan-400">{formatBytes(groupTotals[groupName]?.memory)}</span></span>
                            {#if groupTotals[groupName]?.memoryLimit > 0 && groupTotals[groupName]?.memoryLimit !== groupTotals[groupName]?.memory}
                            <span>LIM: <span class="text-purple-400">{formatBytes(groupTotals[groupName]?.memoryLimit)}</span></span>
                            {/if}
                            <span>RX: <span class="text-cyan-400">{formatBytes(groupTotals[groupName]?.networkRx)}</span></span>
                            <span>TX: <span class="text-cyan-400">{formatBytes(groupTotals[groupName]?.networkTx)}</span></span>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
                        {#each groupContainers as container (container.id)}
                            <div
                                class="relative bg-gray-900/70 border border-gray-800 rounded-xl p-6 hover:border-cyan-500/70 transition-all duration-500 hover:shadow-[0_0_20px_rgba(0,255,204,0.3)] group"
                                use:draggable={{ id: container.id, name: container.name }}
                            >
                                <div
                                    class="absolute top-4 right-4 w-3 h-3 rounded-full {container.status === 'running' ? 'bg-green-400 animate-subtle-pulse' : 'bg-red-500'}"
                                ></div>

                                {#if editingContainerId === container.id}
                                    <div class="flex items-center gap-2 mb-2">
                                        <input 
                                            type="text" 
                                            bind:value={editingName} 
                                            class="bg-gray-800 text-white px-2 py-1 rounded border border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 w-full"
                                            placeholder="Enter container name"
                                        />
                                        <button 
                                            class="text-green-400 hover:text-green-300 transition-colors"
                                            on:click={() => updateContainerName(container.id, editingName)}
                                            title="Save"
                                        >
                                            <IconSave class="w-5 h-5" />
                                        </button>
                                        <button 
                                            class="text-red-400 hover:text-red-300 transition-colors"
                                            on:click={cancelEditing}
                                            title="Cancel"
                                        >
                                            <IconCancel class="w-5 h-5" />
                                        </button>
                                    </div>
                                {:else}
                                    <div class="flex items-center gap-2">
                                        <div class="text-gray-500 cursor-move drag-handle">
                                            <IconDrag class="w-5 h-5" />
                                        </div>
                                        <h3
                                            class="text-xl font-mono text-white group-hover:text-cyan-400 transition-colors duration-300 truncate"
                                        >
                                            {container.name}
                                        </h3>
                                        <button 
                                            class="text-gray-500 hover:text-cyan-300 transition-colors opacity-70 group-hover:opacity-100"
                                            on:click={() => startEditingContainer(container.id, container.name)}
                                            title="Edit container name"
                                        >
                                            <IconEdit class="w-4 h-4" />
                                        </button>
                                        {#if customNames.containers[container.id]}
                                            <button 
                                                class="text-gray-500 hover:text-red-300 transition-colors opacity-70 group-hover:opacity-100"
                                                on:click={() => resetContainerName(container.id)}
                                                title="Reset to original name"
                                            >
                                                <IconReset class="w-4 h-4" />
                                            </button>
                                        {/if}
                                        {#if customNames.container_groups[container.id]}
                                            <button 
                                                class="text-gray-500 hover:text-red-300 transition-colors opacity-70 group-hover:opacity-100"
                                                on:click={() => resetContainerGroup(container.id)}
                                                title="Reset to original group"
                                            >
                                                <IconReset class="w-4 h-4" />
                                            </button>
                                        {/if}
                                    </div>
                                {/if}

                                <p
                                    class="text-sm font-mono text-gray-400 mt-1 capitalize {container.status === 'running' ? 'text-green-400' : 'text-red-400'}"
                                >
                                    {container.status}
                                </p>

                                {#if stats?.[container.id] && container.status === 'running'}
                                    <div class="mt-4 space-y-3 animate-fade-in">
                                        <div>
                                            <p class="text-sm text-gray-300 font-mono">
                                                <IconCpu class="inline w-4 h-4 mr-1" />CPU: <span class="text-cyan-400">{formatCpuInfo(stats[container.id].cpu_percent, stats[container.id].cpu_count, stats[container.id].cpu_limit)}</span>
                                                {#if stats[container.id]?.cpu_shares}
                                                    <span class="text-yellow-400 ml-2">(Shares: {stats[container.id].cpu_shares})</span>
                                                {/if}
                                            </p>
                                            <div class="w-full bg-gray-800 h-2 rounded-full mt-1 relative overflow-hidden">
                                                <div class="bg-cyan-500 h-full rounded-full transition-all duration-500 animate-pulse" style="width: {Math.min(stats[container.id]?.cpu_percent || 0, 100)}%;"></div>
                                                <div class="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent animate-flow"></div>
                                            </div>
                                        </div>
                                        <div>
                                            <p class="text-sm text-gray-300 font-mono">
                                                <IconMemory class="inline w-4 h-4 mr-1" />MEM: <span class="text-cyan-400">{formatBytes(stats[container.id]?.memory_usage || 0)}</span>
                                                {#if stats[container.id]?.memory_limit && stats[container.id]?.memory_limit > 0 && stats[container.id]?.memory_limit !== stats[container.id]?.memory_usage}
                                                 / <span class="text-purple-400">{formatBytes(stats[container.id]?.memory_limit || 0)}</span>
                                                {/if}
                                            </p>
                                            <div class="w-full bg-gray-800 h-2 rounded-full mt-1 relative overflow-hidden">
                                                <div class="bg-cyan-500 h-full rounded-full transition-all duration-500 animate-pulse" style="width: {stats[container.id]?.memory_limit > 0 ? ((stats[container.id]?.memory_usage / stats[container.id]?.memory_limit) * 100).toFixed(1) : 0}%;"></div>
                                                <div class="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent animate-flow"></div>
                                            </div>
                                        </div>
                                        <div class="grid grid-cols-3 gap-2 text-sm text-gray-300 font-mono">
                                            <span>RX: <span class="text-cyan-400">{formatBytes(stats[container.id]?.network_rx || 0)}</span></span>
                                            <span>TX: <span class="text-cyan-400">{formatBytes(stats[container.id]?.network_tx || 0)}</span></span>
                                            <span>I/O R: <span class="text-cyan-400">{formatBytes(stats[container.id]?.io_read || 0)}</span></span>
                                            <span>I/O W: <span class="text-cyan-400">{formatBytes(stats[container.id]?.io_write || 0)}</span></span>
                                            <span>Up: <span class="text-cyan-400">{formatTime(stats[container.id]?.uptime || 0)}</span></span>
                                        </div>
                                    </div>
                                {:else}
                                    <p class="text-sm text-gray-600 font-mono mt-4 animate-pulse">
                                        > Offline or syncing...
                                    </p>
                                {/if}
                            </div>
                        {/each}
                    </div>
                </section>
            {/each}
        </div>
    {:else if viewMode === "list"}
        <div class="w-full max-w-7xl space-y-4">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-4 gap-4">
                <h2 class="text-2xl md:text-3xl font-display text-cyan-400 uppercase tracking-wider">
                    All Containers
                </h2>
                
                <div class="relative flex items-center gap-2">
                    <button 
                        class="sort-button flex items-center gap-2 px-4 py-2 bg-gray-800 rounded-lg text-cyan-400 hover:bg-gray-700 transition-colors"
                        on:click={(e) => {
                            e.stopPropagation();
                            showSortOptions = !showSortOptions;
                        }}
                        title="Select sort field"
                    >
                        <span class="flex items-center gap-1">
                            <svelte:component this={sortOptions.find(opt => opt.field === sortField)?.icon} class="w-5 h-5 mr-1" />
                            Sort: {sortOptions.find(opt => opt.field === sortField)?.label}
                        </span>
                    </button>
                    
                    <button 
                        class="p-2.5 bg-gray-800 rounded-lg text-cyan-400 hover:bg-gray-700 hover:text-white transition-colors"
                        on:click={(e) => {
                            e.stopPropagation();
                            sortDirection = sortDirection === "asc" ? "desc" : "asc";
                            // Save to localStorage
                            try {
                                localStorage.setItem("dockerCoreSort", JSON.stringify({ field: sortField, direction: sortDirection }));
                            } catch (e) {
                                console.error("Failed to save sort preferences", e);
                            }
                        }}
                        title={sortDirection === "asc" ? "Ascending" : "Descending"}
                    >
                        {#if sortDirection === "asc"}
                            <IconSortAsc class="w-5 h-5" />
                        {:else}
                            <IconSortDesc class="w-5 h-5" />
                        {/if}
                    </button>
                    
                    {#if showSortOptions}
                        <div 
                            class="sort-dropdown absolute right-0 top-full mt-2 w-64 bg-gray-800 rounded-lg shadow-lg z-10 py-2 border border-gray-700 animate-fade-in"
                            style="min-width: 100%;"
                            use:clickOutside={() => showSortOptions = false}
                        >
                            {#each sortOptions as option}
                                <button 
                                    class="w-full px-4 py-2 text-left hover:bg-gray-700 flex items-center gap-2 transition-colors {sortField === option.field ? 'text-cyan-400' : 'text-gray-300'}"
                                    on:click={(e) => {
                                        e.stopPropagation();
                                        setSortOption(option.field);
                                    }}
                                >
                                    <svelte:component this={option.icon} class="w-5 h-5" />
                                    {option.label}
                                    {#if sortField === option.field}
                                        <span class="ml-auto text-cyan-400">✓</span>
                                    {/if}
                                </button>
                            {/each}
                        </div>
                    {/if}
                </div>
            </div>
            
            {#each sortedContainers as container}
                <div
                    class="bg-gray-900/70 border border-gray-800 rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between hover:border-cyan-500/70 transition-all duration-500 hover:shadow-[0_0_20px_rgba(0,255,204,0.3)] gap-4 group"
                >
                    <div class="flex items-center space-x-4">
                        <div
                            class="w-3 h-3 rounded-full {container.status === 'running' ? 'bg-green-400 animate-subtle-pulse' : 'bg-red-500'} {sortField === 'status' ? 'ring-2 ring-cyan-400 ring-offset-1 ring-offset-gray-900' : ''}"
                        ></div>
                        
                        {#if editingContainerId === container.id}
                            <div class="flex items-center gap-2">
                                <input 
                                    type="text" 
                                    bind:value={editingName} 
                                    class="bg-gray-800 text-white px-2 py-1 rounded border border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 w-full"
                                    placeholder="Enter container name"
                                />
                                <button 
                                    class="text-green-400 hover:text-green-300 transition-colors"
                                    on:click={() => updateContainerName(container.id, editingName)}
                                    title="Save"
                                >
                                    <IconSave class="w-5 h-5" />
                                </button>
                                <button 
                                    class="text-red-400 hover:text-red-300 transition-colors"
                                    on:click={cancelEditing}
                                    title="Cancel"
                                >
                                    <IconCancel class="w-5 h-5" />
                                </button>
                            </div>
                        {:else}
                            <div class="flex items-center gap-2">
                                <h3 class="text-lg font-mono {sortField === 'name' ? 'text-cyan-400' : 'text-white'} truncate">
                                    {container.name}
                                    {#if sortField === "name"}
                                        {#if sortDirection === "asc"}
                                            <IconSortAsc class="inline w-3 h-3 ml-1" />
                                        {:else}
                                            <IconSortDesc class="inline w-3 h-3 ml-1" />
                                        {/if}
                                    {/if}
                                </h3>
                                <button 
                                    class="text-gray-500 hover:text-cyan-300 transition-colors opacity-70 group-hover:opacity-100"
                                    on:click={() => startEditingContainer(container.id, container.name)}
                                    title="Edit container name"
                                >
                                    <IconEdit class="w-4 h-4" />
                                </button>
                                {#if customNames.containers[container.id]}
                                    <button 
                                        class="text-gray-500 hover:text-red-300 transition-colors opacity-70 group-hover:opacity-100"
                                        on:click={() => resetContainerName(container.id)}
                                        title="Reset to original name"
                                    >
                                        <IconReset class="w-4 h-4" />
                                    </button>
                                {/if}
                            </div>
                        {/if}
                    </div>
                    <div class="text-sm text-gray-300 font-mono flex flex-wrap gap-4 md:gap-6">
                        <span class={sortField === "cpu" ? "text-cyan-400" : ""}>
                            <IconCpu class="inline w-4 h-4 mr-1" />
                            {formatCpuInfo(container.stats?.cpu_percent || 0, container.stats?.cpu_count, container.stats?.cpu_limit)}
                            {#if container.stats?.cpu_shares}
                                <span class="text-yellow-400">(Shares: {container.stats.cpu_shares})</span>
                            {/if}
                            {#if sortField === "cpu"}
                                {#if sortDirection === "asc"}
                                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                                {:else}
                                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                                {/if}
                            {/if}
                        </span>
                        <span class={sortField === "memory" ? "text-cyan-400" : ""}>
                            <IconMemory class="inline w-4 h-4 mr-1" />
                            {formatBytes(container.stats?.memory_usage || 0)}
                            {#if container.stats?.memory_limit && container.stats?.memory_limit > 0 && container.stats?.memory_limit !== container.stats?.memory_usage}
                             / {formatBytes(container.stats?.memory_limit || 0)}
                            {/if}
                            {#if sortField === "memory"}
                                {#if sortDirection === "asc"}
                                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                                {:else}
                                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                                {/if}
                            {/if}
                        </span>
                        <span class={sortField === "network_rx" ? "text-cyan-400" : ""}>
                            RX: {formatBytes(container.stats?.network_rx || 0)}
                            {#if sortField === "network_rx"}
                                {#if sortDirection === "asc"}
                                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                                {:else}
                                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                                {/if}
                            {/if}
                        </span>
                        <span class={sortField === "network_tx" ? "text-cyan-400" : ""}>
                            TX: {formatBytes(container.stats?.network_tx || 0)}
                            {#if sortField === "network_tx"}
                                {#if sortDirection === "asc"}
                                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                                {:else}
                                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                                {/if}
                            {/if}
                        </span>
                        <span class={sortField === "io_read" || sortField === "io_write" ? "text-cyan-400" : ""}>
                            I/O: {formatBytes(container.stats?.io_read || 0)}/{formatBytes(container.stats?.io_write || 0)}
                            {#if sortField === "io_read" || sortField === "io_write"}
                                {#if sortDirection === "asc"}
                                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                                {:else}
                                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                                {/if}
                            {/if}
                        </span>
                        <span class={sortField === "uptime" ? "text-cyan-400" : ""}>
                            {formatTime(container.stats?.uptime || 0)}
                            {#if sortField === "uptime"}
                                {#if sortDirection === "asc"}
                                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                                {:else}
                                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                                {/if}
                            {/if}
                        </span>
                    </div>
                </div>
            {/each}
        </div>
    {/if}

    <div class="fixed inset-0 -z-10 pointer-events-none">
        <div class="absolute inset-0 bg-gradient-to-b from-gray-950 to-gray-900 opacity-90"></div>
        <div class="absolute top-0 left-0 w-full h-full bg-[radial-gradient(circle_at_50%_50%,rgba(0,255,204,0.1),transparent_70%)]"></div>
    </div>

    <!-- Add connection status indicator -->
    {#if connectionError}
    <div class="fixed bottom-4 right-4 bg-red-600 text-white px-4 py-3 rounded-md shadow-lg z-50 flex items-start">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2 mt-0.5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
        </svg>
        <div class="flex flex-col">
            <span class="font-medium">{errorMessage}</span>
            {#if reconnectAttempts < maxReconnectAttempts}
                <span class="text-sm opacity-90 mt-1">Reconnecting ({reconnectAttempts}/{maxReconnectAttempts})...</span>
            {:else}
                <span class="text-sm opacity-90 mt-1">
                    Please check if Docker is running and accessible.
                    <button 
                        class="underline ml-1 hover:text-white/80 transition-colors" 
                        on:click={() => window.location.reload()}
                    >
                        Refresh page
                    </button>
                </span>
            {/if}
        </div>
        <button 
            class="ml-3 text-white/80 hover:text-white transition-colors"
            on:click={() => connectionError = false}
        >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
            </svg>
        </button>
    </div>
    {/if}
</main>

<style>
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .animate-fade-in {
        animation: fadeIn 0.5s ease-out forwards;
    }

    @keyframes flow {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
    }
    .animate-flow {
        animation: flow 3s infinite linear;
    }

    @keyframes subtlePulse {
        0% { transform: scale(1); opacity: 0.8; }
        50% { transform: scale(1.2); opacity: 1; }
        100% { transform: scale(1); opacity: 0.8; }
    }
    .animate-subtle-pulse {
        animation: subtlePulse 2s infinite ease-in-out;
    }

    /* These classes are used by the draggable and dropZone directives */
    :global(.dragging) {
        opacity: 0.5;
        cursor: move;
    }
    
    :global(.drop-target) {
        border-color: rgba(0, 255, 204, 0.7);
        box-shadow: 0 0 20px rgba(0, 255, 204, 0.3);
    }
    
    .drag-handle {
        cursor: grab;
    }
    
    .drag-handle:active {
        cursor: grabbing;
    }
</style>