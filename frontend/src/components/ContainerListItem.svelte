<!-- src/components/ContainerListItem.svelte -->
<script lang="ts">
    import { formatBytes, formatCpuInfo, formatTime } from '$lib/utils/formatters';
    import { stats, editingContainerId, editingName, sortField, sortDirection } from '../stores/containerStore';
    import { startEditing, stopEditing } from '../stores/containerStore';
    import { updateContainerName, resetContainerName } from '../api/containerService';
    import type { Container } from '$lib/types';
    
    // Íconos de Material Design
    import IconCpu from '~icons/mdi/monitor';
    import IconMemory from '~icons/mdi/memory';
    import IconEdit from '~icons/mdi/pencil';
    import IconSave from '~icons/mdi/content-save';
    import IconCancel from '~icons/mdi/close';
    import IconReset from '~icons/mdi/refresh';
    import IconSortAsc from '~icons/mdi/sort-ascending';
    import IconSortDesc from '~icons/mdi/sort-descending';
    
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
            const success = await updateContainerName(container.id, $editingName);
            if (success) {
                // Update local state
                customNames.containers[container.id] = $editingName;
                customNames = customNames;
            }
            cancelEditing();
        }
    }
    
    async function handleResetContainerName() {
        const success = await resetContainerName(container.id);
        if (success) {
            // Update local state
            delete customNames.containers[container.id];
            customNames = customNames;
        }
    }
</script>

<div
    class="bg-gray-900/70 border border-gray-800 rounded-xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between hover:border-cyan-500/70 transition-all duration-500 hover:shadow-[0_0_20px_rgba(0,255,204,0.3)] gap-4 group"
>
    <div class="flex items-center space-x-4">
        <div
            class="w-3 h-3 rounded-full {container.status === 'running' ? 'bg-green-400 animate-subtle-pulse' : 'bg-red-500'} {$sortField === 'status' ? 'ring-2 ring-cyan-400 ring-offset-1 ring-offset-gray-900' : ''}"
        ></div>
        
        {#if $editingContainerId === container.id}
            <div class="flex items-center gap-2">
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
                <h3 class="text-lg font-mono {$sortField === 'name' ? 'text-cyan-400' : 'text-white'} truncate">
                    {container.name}
                    {#if $sortField === "name"}
                        {#if $sortDirection === "asc"}
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
                        on:click={handleResetContainerName}
                        title="Reset to original name"
                    >
                        <IconReset class="w-4 h-4" />
                    </button>
                {/if}
            </div>
        {/if}
    </div>
    <div class="text-sm text-gray-300 font-mono flex flex-wrap gap-4 md:gap-6">
        <span class={$sortField === "cpu" ? "text-cyan-400" : ""}>
            <IconCpu class="inline w-4 h-4 mr-1" />
            {formatCpuInfo($stats?.[container.id]?.cpu_percent || 0, $stats?.[container.id]?.cpu_count, $stats?.[container.id]?.cpu_limit)}
            {#if $stats?.[container.id]?.cpu_shares}
                <span class="text-yellow-400">(Shares: {$stats[container.id].cpu_shares})</span>
            {/if}
            {#if $sortField === "cpu"}
                {#if $sortDirection === "asc"}
                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                {:else}
                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                {/if}
            {/if}
        </span>
        <span class={$sortField === "memory" ? "text-cyan-400" : ""}>
            <IconMemory class="inline w-4 h-4 mr-1" />
            {formatBytes($stats?.[container.id]?.memory_usage || 0)}
            {#if $stats?.[container.id]?.memory_limit && $stats?.[container.id]?.memory_limit > 0 && $stats?.[container.id]?.memory_limit !== $stats?.[container.id]?.memory_usage}
             / {formatBytes($stats?.[container.id]?.memory_limit || 0)}
            {/if}
            {#if $sortField === "memory"}
                {#if $sortDirection === "asc"}
                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                {:else}
                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                {/if}
            {/if}
        </span>
        <span class={$sortField === "network_rx" ? "text-cyan-400" : ""}>
            RX: {formatBytes($stats?.[container.id]?.network_rx || 0)}
            {#if $sortField === "network_rx"}
                {#if $sortDirection === "asc"}
                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                {:else}
                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                {/if}
            {/if}
        </span>
        <span class={$sortField === "network_tx" ? "text-cyan-400" : ""}>
            TX: {formatBytes($stats?.[container.id]?.network_tx || 0)}
            {#if $sortField === "network_tx"}
                {#if $sortDirection === "asc"}
                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                {:else}
                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                {/if}
            {/if}
        </span>
        <span class={$sortField === "io_read" || $sortField === "io_write" ? "text-cyan-400" : ""}>
            I/O: {formatBytes($stats?.[container.id]?.io_read || 0)}/{formatBytes($stats?.[container.id]?.io_write || 0)}
            {#if $sortField === "io_read" || $sortField === "io_write"}
                {#if $sortDirection === "asc"}
                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                {:else}
                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                {/if}
            {/if}
        </span>
        <span class={$sortField === "uptime" ? "text-cyan-400" : ""}>
            {formatTime($stats?.[container.id]?.uptime || 0)}
            {#if $sortField === "uptime"}
                {#if $sortDirection === "asc"}
                    <IconSortAsc class="inline w-3 h-3 ml-1" />
                {:else}
                    <IconSortDesc class="inline w-3 h-3 ml-1" />
                {/if}
            {/if}
        </span>
    </div>
</div> 