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

    const API_URL = env.PUBLIC_API_URL ?? 'http://localhost:5000';
    const SOCKET_URL = env.PUBLIC_SOCKET_URL ?? 'http://localhost:5000';
    const REFRESH_INTERVAL = parseInt(env.PUBLIC_REFRESH_INTERVAL ?? '10000');

    let containers: Container[] = [];
    let stats: Record<string, Stats> = {};
    let intervalId: number | undefined;
    let networkHistory: NetworkHistory = { rx: [], tx: [] };
    let viewMode: "groups" | "list" = "groups";
    let systemInfo: { MemTotal: number, NCPU: number } = { MemTotal: 0, NCPU: 0 };
    
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

    async function fetchContainers() {
        const res = await fetch(`${API_URL}/containers`);
        containers = await res.json();
    }

    async function startMonitoring() {
        await fetch(`${API_URL}/start`);
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

        const socket = io(SOCKET_URL);
        socket.on("connect", () => {
            console.log("Connected to WebSocket");
        });
        socket.on("update_stats", (data: { containers: Record<string, Stats>, system_info: { MemTotal: number, NCPU: number } }) => {
            stats = data.containers || {};
            systemInfo = data.system_info || { MemTotal: 0, NCPU: 0 };
            const totalRx = Object.values(stats).reduce((sum, stat) => sum + stat.network_rx, 0);
            const totalTx = Object.values(stats).reduce((sum, stat) => sum + stat.network_tx, 0);
            networkHistory.rx = [...networkHistory.rx.slice(-9), totalRx].slice(-10);
            networkHistory.tx = [...networkHistory.tx.slice(-9), totalTx].slice(-10);
        });

        intervalId = setInterval(fetchContainers, REFRESH_INTERVAL);

        return () => {
            socket.disconnect();
            if (intervalId) clearInterval(intervalId);
            if (networkChart) networkChart.destroy();
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

    $: groupedContainers = (containers || []).reduce((acc: Record<string, Container[]>, container) => {
        const prefix = container.name.split(/[-_]/)[0] || container.name;
        acc[prefix] = acc[prefix] || [];
        acc[prefix].push(container);
        return acc;
    }, {});

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
                    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2">
                        <h2 class="text-2xl md:text-3xl font-display text-cyan-400 uppercase tracking-wider">
                            {groupName}
                        </h2>
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
                            >
                                <div
                                    class="absolute top-4 right-4 w-3 h-3 rounded-full {container.status === 'running' ? 'bg-green-400 animate-subtle-pulse' : 'bg-red-500'}"
                                ></div>

                                <h3
                                    class="text-xl font-mono text-white group-hover:text-cyan-400 transition-colors duration-300 truncate"
                                >
                                    {container.name}
                                </h3>

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
                    class="bg-gray-900/70 border border-gray-800 rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between hover:border-cyan-500/70 transition-all duration-500 hover:shadow-[0_0_20px_rgba(0,255,204,0.3)] gap-4"
                >
                    <div class="flex items-center space-x-4">
                        <div
                            class="w-3 h-3 rounded-full {container.status === 'running' ? 'bg-green-400 animate-subtle-pulse' : 'bg-red-500'} {sortField === 'status' ? 'ring-2 ring-cyan-400 ring-offset-1 ring-offset-gray-900' : ''}"
                        ></div>
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
</style>