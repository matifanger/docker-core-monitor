<!-- src/components/ContainerCard.svelte -->
<script lang="ts">
    import { draggable } from '../directives/interaction';
    import { formatBytes, formatCpuInfo, formatTime } from '$lib/utils/formatters';
    import { stats, editingContainerId, editingName } from '../stores/containerStore';
    import { startEditing, stopEditing } from '../stores/containerStore';
    import { updateContainerName, resetContainerName, resetContainerGroup } from '../api/containerService';
    import type { Container } from '$lib/types';
    
    // Íconos de Material Design
    import IconCpu from '~icons/mdi/monitor';
    import IconMemory from '~icons/mdi/memory';
    import IconEdit from '~icons/mdi/pencil';
    import IconSave from '~icons/mdi/content-save';
    import IconCancel from '~icons/mdi/close';
    import IconReset from '~icons/mdi/refresh';
    import IconDrag from '~icons/mdi/drag';
    
    export let container: Container;
    export let customNames: { 
        containers: Record<string, string>, 
        groups: Record<string, string>,
        container_groups: Record<string, string>
    };
    
    function startEditingContainer(containerId: string, currentName: string) {
        startEditing();
        editingContainerId.set(containerId);
        editingName.set(currentName);
    }
    
    function cancelEditing() {
        editingContainerId.set(null);
        editingName.set('');
        stopEditing();
    }
    
    async function handleUpdateContainerName() {
        if ($editingContainerId === container.id) {
            const success = await updateContainerName(container.docker_name, $editingName);
            if (success) {
                // Update local state
                customNames.containers[container.docker_name] = $editingName;
                customNames = customNames;
            }
            cancelEditing();
        }
    }
    
    async function handleResetContainerName() {
        const success = await resetContainerName(container.docker_name);
        if (success) {
            // Update local state
            delete customNames.containers[container.docker_name];
            customNames = customNames;
        }
    }
    
    async function handleResetContainerGroup() {
        const success = await resetContainerGroup(container.docker_name);
        if (success) {
            // Update local state
            delete customNames.container_groups[container.docker_name];
            customNames = customNames;
        }
    }
</script>

<div
    class="relative bg-gray-900/70 border border-gray-800 rounded-xl p-6 hover:border-cyan-500/70 transition-all duration-500 hover:shadow-[0_0_20px_rgba(0,255,204,0.3)] group"
    use:draggable={{ id: container.id, name: container.name }}
>
    <div
        class="absolute top-4 right-4 w-3 h-3 rounded-full {container.status === 'running' ? 'bg-green-400 animate-subtle-pulse' : 'bg-red-500'}"
    ></div>

    {#if $editingContainerId === container.id}
        <div class="flex items-center gap-2 mb-2">
            <input 
                type="text" 
                bind:value={$editingName} 
                class="bg-gray-800 text-white px-2 py-1 rounded border border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 w-full"
                placeholder="Enter container name"
            />
            <button 
                class="text-green-400 hover:text-green-300 transition-colors"
                on:click={handleUpdateContainerName}
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
            {#if customNames.containers[container.docker_name]}
                <button 
                    class="text-gray-500 hover:text-red-300 transition-colors opacity-70 group-hover:opacity-100"
                    on:click={handleResetContainerName}
                    title="Reset to original name"
                >
                    <IconReset class="w-4 h-4" />
                </button>
            {/if}
            {#if customNames.container_groups[container.docker_name]}
                <button 
                    class="text-gray-500 hover:text-red-300 transition-colors opacity-70 group-hover:opacity-100"
                    on:click={handleResetContainerGroup}
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

    {#if $stats?.[container.id] && container.status === 'running'}
        <div class="mt-4 space-y-3 animate-fade-in">
            <div>
                <p class="text-sm text-gray-300 font-mono">
                    <IconCpu class="inline w-4 h-4 mr-1" />CPU: <span class="text-cyan-400">{formatCpuInfo($stats[container.id].cpu_percent, $stats[container.id].cpu_count, $stats[container.id].cpu_limit)}</span>
                    {#if $stats[container.id]?.cpu_shares}
                        <span class="text-yellow-400 ml-2">(Shares: {$stats[container.id].cpu_shares})</span>
                    {/if}
                </p>
                <div class="w-full bg-gray-800 h-2 rounded-full mt-1 relative overflow-hidden">
                    <div class="bg-cyan-500 h-full rounded-full transition-all duration-500 animate-pulse" style="width: {Math.min($stats[container.id]?.cpu_percent || 0, 100)}%;"></div>
                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent animate-flow"></div>
                </div>
            </div>
            <div>
                <p class="text-sm text-gray-300 font-mono">
                    <IconMemory class="inline w-4 h-4 mr-1" />MEM: <span class="text-cyan-400">{formatBytes($stats[container.id]?.memory_usage || 0)}</span>
                    {#if $stats[container.id]?.memory_limit && $stats[container.id]?.memory_limit > 0 && $stats[container.id]?.memory_limit !== $stats[container.id]?.memory_usage}
                     / <span class="text-purple-400">{formatBytes($stats[container.id]?.memory_limit || 0)}</span>
                    {/if}
                </p>
                <div class="w-full bg-gray-800 h-2 rounded-full mt-1 relative overflow-hidden">
                    <div class="bg-cyan-500 h-full rounded-full transition-all duration-500 animate-pulse" style="width: {$stats[container.id]?.memory_limit > 0 ? (($stats[container.id]?.memory_usage / $stats[container.id]?.memory_limit) * 100).toFixed(1) : 0}%;"></div>
                    <div class="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent animate-flow"></div>
                </div>
            </div>
            <div class="grid grid-cols-3 gap-2 text-sm text-gray-300 font-mono">
                <span>RX: <span class="text-cyan-400">{formatBytes($stats[container.id]?.network_rx || 0)}</span></span>
                <span>TX: <span class="text-cyan-400">{formatBytes($stats[container.id]?.network_tx || 0)}</span></span>
                <span>I/O R: <span class="text-cyan-400">{formatBytes($stats[container.id]?.io_read || 0)}</span></span>
                <span>I/O W: <span class="text-cyan-400">{formatBytes($stats[container.id]?.io_write || 0)}</span></span>
                <span>Up: <span class="text-cyan-400">{formatTime($stats[container.id]?.uptime || 0)}</span></span>
            </div>
        </div>
    {:else}
        <p class="text-sm text-gray-600 font-mono mt-4 animate-pulse">
            > Offline or syncing...
        </p>
    {/if}
</div> 