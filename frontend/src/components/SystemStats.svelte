<!-- src/components/SystemStats.svelte -->
<script lang="ts">
    import { totalStats } from '../stores/containerStore';
    import { formatBytes, formatCpuInfo } from '$lib/utils/formatters';
    
    // Íconos de Material Design
    import IconCpu from '~icons/mdi/monitor';
    import IconMemory from '~icons/mdi/memory';
    import IconNetwork from '~icons/mdi/network';
    import IconHardDrive from '~icons/mdi/harddisk';
    
    import NetworkChart from './NetworkChart.svelte';
</script>

<div class="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6 text-gray-300 font-mono text-sm">
    <div class="space-y-4">
        <div>
            <p><IconCpu class="inline w-4 h-4 mr-1" />CPU: <span class="text-cyan-400">{formatCpuInfo($totalStats.cpuPercent, $totalStats.cpuCount, null)}</span></p>
            <div class="w-full bg-gray-800 h-3 rounded-full mt-1 relative overflow-hidden">
                <div class="bg-cyan-500 h-full rounded-full transition-all duration-500 animate-pulse" style="width: {Math.min($totalStats.cpuPercent, 100)}%;"></div>
                <div class="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent animate-flow"></div>
            </div>
        </div>
        <div>
            <p><IconMemory class="inline w-4 h-4 mr-1" />Memory: <span class="text-cyan-400">{formatBytes($totalStats.memoryUsage)}</span>
            {#if $totalStats.memoryLimit > 0 && $totalStats.memoryLimit !== $totalStats.memoryUsage}
             / <span class="text-purple-400">{formatBytes($totalStats.memoryLimit)}</span>
            {/if}
            </p>
            <div class="w-full bg-gray-800 h-3 rounded-full mt-1 relative overflow-hidden">
                <div class="bg-cyan-500 h-full rounded-full transition-all duration-500 animate-pulse" style="width: {$totalStats.memoryLimit > 0 ? (($totalStats.memoryUsage / $totalStats.memoryLimit) * 100).toFixed(1) : 0}%;"></div>
                <div class="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-500/20 to-transparent animate-flow"></div>
            </div>
        </div>
        <p><IconHardDrive class="inline w-4 h-4 mr-1" />I/O Read: <span class="text-cyan-400">{formatBytes($totalStats.ioRead)}</span></p>
        <p><IconHardDrive class="inline w-4 h-4 mr-1" />I/O Write: <span class="text-cyan-400">{formatBytes($totalStats.ioWrite)}</span></p>
    </div>
    <div class="space-y-4">
        <p class="text-cyan-400"><IconNetwork class="inline w-4 h-4 mr-1" />Network Flow</p>
        <NetworkChart />
        <p>RX: <span class="text-cyan-400">{formatBytes($totalStats.networkRx)}</span> | TX: <span class="text-pink-500">{formatBytes($totalStats.networkTx)}</span></p>
    </div>
</div> 