<!-- src/components/SortOptions.svelte -->
<script lang="ts">
    import { clickOutside } from '../directives/interaction';
    import { sortField, sortDirection, showSortOptions } from '../stores/containerStore';
    import { savePreferences } from '../stores/containerStore';
    import type { SortField, SortDirection } from '../stores/containerStore';
    
    // Íconos de Material Design
    import IconSort from '~icons/mdi/sort';
    import IconSortAsc from '~icons/mdi/sort-ascending';
    import IconSortDesc from '~icons/mdi/sort-descending';
    import IconCpu from '~icons/mdi/monitor';
    import IconMemory from '~icons/mdi/memory';
    import IconNetwork from '~icons/mdi/network';
    import IconHardDrive from '~icons/mdi/harddisk';
    import IconClock from '~icons/mdi/clock';
    import IconName from '~icons/mdi/alphabetical';
    
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
    
    function setSortOption(field: SortField) {
        if ($sortField === field) {
            // Toggle direction if same field
            const newDirection = $sortDirection === "asc" ? "desc" : "asc";
            sortDirection.set(newDirection);
            savePreferences('SortDirection', newDirection);
        } else {
            sortField.set(field);
            // Default directions based on field type
            const newDirection = (field === "name" || field === "status") ? "asc" : "desc";
            sortDirection.set(newDirection);
            
            // Save to localStorage
            savePreferences('SortField', field);
            savePreferences('SortDirection', newDirection);
        }
        
        // Close dropdown with a small delay to avoid flickering
        setTimeout(() => {
            showSortOptions.set(false);
        }, 100);
    }
</script>

<div class="relative flex items-center gap-2">
    <button 
        class="sort-button flex items-center gap-2 px-4 py-2 bg-gray-800 rounded-lg text-cyan-400 hover:bg-gray-700 transition-colors"
        on:click={(e) => {
            e.stopPropagation();
            showSortOptions.set(!$showSortOptions);
        }}
        title="Select sort field"
    >
        <span class="flex items-center gap-1">
            <svelte:component this={sortOptions.find(opt => opt.field === $sortField)?.icon} class="w-5 h-5 mr-1" />
            Sort: {sortOptions.find(opt => opt.field === $sortField)?.label}
        </span>
    </button>
    
    <button 
        class="p-2.5 bg-gray-800 rounded-lg text-cyan-400 hover:bg-gray-700 hover:text-white transition-colors"
        on:click={(e) => {
            e.stopPropagation();
            const newDirection = $sortDirection === "asc" ? "desc" : "asc";
            sortDirection.set(newDirection);
            // Save to localStorage
            savePreferences('SortDirection', newDirection);
        }}
        title={$sortDirection === "asc" ? "Ascending" : "Descending"}
    >
        {#if $sortDirection === "asc"}
            <IconSortAsc class="w-5 h-5" />
        {:else}
            <IconSortDesc class="w-5 h-5" />
        {/if}
    </button>
    
    {#if $showSortOptions}
        <div 
            class="sort-dropdown absolute right-0 top-full mt-2 w-64 bg-gray-800 rounded-lg shadow-lg z-10 py-2 border border-gray-700 animate-fade-in"
            style="min-width: 100%;"
            use:clickOutside={() => showSortOptions.set(false)}
        >
            {#each sortOptions as option}
                <button 
                    class="w-full px-4 py-2 text-left hover:bg-gray-700 flex items-center gap-2 transition-colors {$sortField === option.field ? 'text-cyan-400' : 'text-gray-300'}"
                    on:click={(e) => {
                        e.stopPropagation();
                        setSortOption(option.field);
                    }}
                >
                    <svelte:component this={option.icon} class="w-5 h-5" />
                    {option.label}
                    {#if $sortField === option.field}
                        <span class="ml-auto text-cyan-400">✓</span>
                    {/if}
                </button>
            {/each}
        </div>
    {/if}
</div> 