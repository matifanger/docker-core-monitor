<!-- src/routes/+page.svelte -->
<script lang="ts">
    import { onMount, onDestroy } from "svelte";
    import { io } from "socket.io-client";
    import type { Container } from '$lib/types';
    import { env } from '$env/dynamic/public';
    import { browser } from '$app/environment';
    
    // Components
    import SystemStats from '../components/SystemStats.svelte';
    import ContainerGroup from '../components/ContainerGroup.svelte';
    import ContainerListItem from '../components/ContainerListItem.svelte';
    import SortOptions from '../components/SortOptions.svelte';
    
    // Stores
    import { 
        containers, stats, customNames, systemInfo, viewMode,
        sortedGroups, sortedContainers, updateNetworkHistory,
        initializeStoresFromLocalStorage, savePreferences,
        startEditing, stopEditing, startDragging, stopDragging
    } from '../stores/containerStore';
    
    // API
    import { fetchContainers, fetchCustomNames } from '../api/containerService';
    
    // Icons
    import IconGrid from '~icons/mdi/grid';
    import IconList from '~icons/mdi/format-list-bulleted';
    
    const API_URL = env.PUBLIC_API_URL ?? 'http://localhost:5000';
    const SOCKET_URL = env.PUBLIC_SOCKET_URL ?? 'http://localhost:5000';
    const REFRESH_INTERVAL = parseInt(env.PUBLIC_REFRESH_INTERVAL ?? '10000');
    
    let intervalId: ReturnType<typeof setInterval> | undefined;
    
    // Make these functions available globally for the directives, but only in the browser
    if (browser) {
        window.startEditing = startEditing;
        window.stopEditing = stopEditing;
        window.startDragging = startDragging;
        window.stopDragging = stopDragging;
    }

    onMount(() => {
        // Initialize stores from localStorage
        initializeStoresFromLocalStorage();
        
        // Initial data fetch
        const fetchInitialData = async () => {
            const containersData = await fetchContainers();
            containers.set(containersData);
            
            const namesData = await fetchCustomNames();
            customNames.set(namesData);
        };
        
        fetchInitialData();
        
        // Setup socket connection
        const socket = io(SOCKET_URL, {
            transports: ['websocket'],
            reconnectionDelay: 200,
            timeout: 20000,
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelayMax: 5000,
            autoConnect: true
        });

        console.log("Connecting to server...");

        socket.on('connect', () => {
            console.log('Connected to server');
            // Request stats immediately on connect
            socket.emit('request_stats');
            // Force a container update
            fetchContainers().then(data => {
                containers.set(data);
            });
        });

        socket.on('connect_error', (error) => {
            console.error('Connection error:', error);
        });

        socket.on('reconnect', (attemptNumber) => {
            console.log(`Reconnected after ${attemptNumber} attempts`);
            // Request stats immediately on reconnect
            socket.emit('request_stats');
            // Force a container update
            fetchContainers().then(data => {
                containers.set(data);
            });
        });

        socket.on('disconnect', (reason) => {
            console.warn(`Disconnected: ${reason}`);
            if (reason === 'io server disconnect') {
                // Server closed the connection, try to reconnect manually
                socket.connect();
            }
        });

        socket.on("update_stats", (data: { 
            containers: Record<string, any>, 
            system_info: { MemTotal: number, NCPU: number },
            custom_names: { 
                containers: Record<string, string>, 
                groups: Record<string, string>,
                container_groups: Record<string, string>
            }
        }) => {
            // Update stats
            stats.set(data.containers);
            systemInfo.set(data.system_info);
            
            // Update network history
            updateNetworkHistory(data.containers);
            
            // Update custom names if not editing
            if (document.activeElement?.tagName !== 'INPUT') {
                customNames.set(data.custom_names);
            }
        });

        // Set up refresh interval for containers
        intervalId = setInterval(async () => {
            const data = await fetchContainers();
            containers.set(data);
        }, REFRESH_INTERVAL);

        // Clean up function
        return () => {
            socket.disconnect();
            if (intervalId) clearInterval(intervalId);
        };
    });

    onDestroy(() => {
        if (intervalId) clearInterval(intervalId);
    });
    
    function toggleViewMode() {
        viewMode.update(current => {
            const newMode = current === 'groups' ? 'list' : 'groups';
            // Save view mode to localStorage
            savePreferences('ViewMode', newMode);
            return newMode;
        });
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
                on:click={toggleViewMode}
            >
                {#if $viewMode === 'groups'}
                    <IconList class="w-6 h-6" />
                {:else}
                    <IconGrid class="w-6 h-6" />
                {/if}
            </button>
        </div>
        
        <SystemStats />
    </header>

    {#if $containers.length === 0}
        <div class="text-gray-500 text-xl font-mono animate-pulse">
            > No systems online...
        </div>
    {:else if $viewMode === "groups"}
        <div class="w-full max-w-7xl space-y-8">
            {#each $sortedGroups as [groupName, groupContainers]}
                <ContainerGroup 
                    {groupName} 
                    containers={groupContainers} 
                    customNames={$customNames} 
                />
            {/each}
        </div>
    {:else if $viewMode === "list"}
        <div class="w-full max-w-7xl space-y-4">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-4 gap-4">
                <h2 class="text-2xl md:text-3xl font-display text-cyan-400 uppercase tracking-wider">
                    All Containers
                </h2>
                
                <SortOptions />
            </div>
            
            {#each $sortedContainers as container}
                <ContainerListItem {container} customNames={$customNames} />
            {/each}
        </div>
    {/if}

    <div class="fixed inset-0 -z-10 pointer-events-none">
        <div class="absolute inset-0 bg-gradient-to-b from-gray-950 to-gray-900 opacity-90"></div>
        <div class="absolute top-0 left-0 w-full h-full bg-[radial-gradient(circle_at_50%_50%,rgba(0,255,204,0.1),transparent_70%)]"></div>
    </div>
</main>

<style>
    /* These classes are used by the draggable and dropZone directives */
    :global(.dragging) {
        opacity: 0.5;
        cursor: move;
    }
    
    :global(.drop-target) {
        border-color: rgba(0, 255, 204, 0.7);
        box-shadow: 0 0 20px rgba(0, 255, 204, 0.3);
    }
</style>