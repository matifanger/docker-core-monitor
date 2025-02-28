<!-- src/components/ContainerGroup.svelte -->
<script lang="ts">
    import { dropZone } from '../directives/interaction';
    import { formatBytes, formatCpuInfo } from '$lib/utils/formatters';
    import { editingGroupName, editingName, groupTotals } from '../stores/containerStore';
    import { startEditing, stopEditing } from '../stores/containerStore';
    import { updateGroupName, resetGroupName, updateContainerGroup } from '../api/containerService';
    import type { Container } from '$lib/types';
    import ContainerCard from './ContainerCard.svelte';
    
    // Íconos de Material Design
    import IconEdit from '~icons/mdi/pencil';
    import IconSave from '~icons/mdi/content-save';
    import IconCancel from '~icons/mdi/close';
    import IconReset from '~icons/mdi/refresh';
    
    export let groupName: string;
    export let containers: Container[];
    export let customNames: { 
        containers: Record<string, string>, 
        groups: Record<string, string>,
        container_groups: Record<string, string>
    };
    
    function startEditingGroup(groupName: string, currentName: string) {
        startEditing();
        editingGroupName.set(groupName);
        editingName.set(currentName);
    }
    
    function cancelEditing() {
        editingGroupName.set(null);
        editingName.set('');
        stopEditing();
    }
    
    async function handleUpdateGroupName() {
        if ($editingGroupName === groupName) {
            const success = await updateGroupName(groupName, $editingName);
            if (success) {
                // Update local state
                customNames.groups[groupName] = $editingName;
                customNames = customNames;
            }
            cancelEditing();
        }
    }
    
    async function handleResetGroupName() {
        const success = await resetGroupName(groupName);
        if (success) {
            // Update local state
            delete customNames.groups[groupName];
            customNames = customNames;
        }
    }
    
    function handleContainerDrop(data: Record<string, unknown>) {
        // Type check the data
        if (typeof data.id !== 'string' || typeof data.name !== 'string') {
            console.error('Invalid drop data', data);
            return;
        }
        
        const currentGroup = getContainerGroup(data.id);
        if (currentGroup === groupName) {
            return; // Already in this group
        }
        
        // Update local state immediately
        customNames.container_groups[data.id] = groupName;
        customNames = customNames;
        
        // Then update on the server
        updateContainerGroup(data.id, groupName);
    }
    
    function getContainerGroup(containerId: string): string {
        // First check if there's a custom group assignment
        if (customNames.container_groups[containerId]) {
            return customNames.container_groups[containerId];
        }
        
        // Otherwise use the default grouping based on name
        const container = containers.find(c => c.id === containerId);
        if (!container) return "Unknown";
        
        // Default group is the first part of the name before any dash or underscore
        return container.name.split(/[-_]/)[0] || container.name;
    }
    
    function getGroupDisplayName(groupName: string): string {
        return customNames.groups[groupName] || groupName;
    }
</script>

<section class="space-y-4">
    <div class="flex items-center justify-between border-b border-cyan-500/20 pb-2"
         use:dropZone={{ onDrop: handleContainerDrop }}>
        <div class="flex items-center gap-2">
            {#if $editingGroupName === groupName}
                <div class="flex items-center gap-2">
                    <input 
                        type="text" 
                        bind:value={$editingName} 
                        class="bg-gray-800 text-white px-2 py-1 rounded border border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500 min-w-[200px]"
                        placeholder="Enter group name"
                    />
                    <button 
                        class="text-green-400 hover:text-green-300 transition-colors"
                        on:click={handleUpdateGroupName}
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
                            on:click={handleResetGroupName}
                            title="Reset to original name"
                        >
                            <IconReset class="w-5 h-5" />
                        </button>
                    {/if}
                </h2>
            {/if}
        </div>
        <div class="hidden md:flex space-x-4 text-sm text-gray-300 font-mono">
            <span>CPU: <span class="text-cyan-400">{formatCpuInfo($groupTotals[groupName]?.cpu, $groupTotals[groupName]?.cpuCount, null)}</span></span>
            <span>MEM: <span class="text-cyan-400">{formatBytes($groupTotals[groupName]?.memory)}</span></span>
            {#if $groupTotals[groupName]?.memoryLimit > 0 && $groupTotals[groupName]?.memoryLimit !== $groupTotals[groupName]?.memory}
            <span>LIM: <span class="text-purple-400">{formatBytes($groupTotals[groupName]?.memoryLimit)}</span></span>
            {/if}
            <span>RX: <span class="text-cyan-400">{formatBytes($groupTotals[groupName]?.networkRx)}</span></span>
            <span>TX: <span class="text-cyan-400">{formatBytes($groupTotals[groupName]?.networkTx)}</span></span>
        </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
        {#each containers as container (container.id)}
            <ContainerCard {container} {customNames} />
        {/each}
    </div>
</section> 