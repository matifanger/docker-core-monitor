<!-- src/components/NetworkChart.svelte -->
<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { Chart } from 'chart.js/auto';
    import { chartData } from '../stores/containerStore';
    import { formatBytes } from '$lib/utils/formatters';
    import { browser } from '$app/environment';
    
    let chartElement: HTMLCanvasElement;
    let chart: Chart;
    let unsubscribe: () => void;
    
    onMount(() => {
        if (!browser || !chartElement) return;
        
        // Initialize chart
        chart = new Chart(chartElement, {
            type: 'line',
            data: {
                labels: Array(10).fill(''),
                datasets: [
                    {
                        label: 'RX (Download)',
                        data: Array(10).fill(0),
                        borderColor: 'rgba(75, 192, 192, 1)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        tension: 0.4,
                        fill: true
                    },
                    {
                        label: 'TX (Upload)',
                        data: Array(10).fill(0),
                        borderColor: 'rgba(255, 99, 132, 1)',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        tension: 0.4,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 300  // Reduce animation duration for faster updates
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: '#fff',
                            callback: function(value) {
                                return formatBytes(Number(value));
                            }
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
                            label: function(context) {
                                return `${context.dataset.label}: ${formatBytes(Number(context.raw))}`;
                            }
                        }
                    }
                }
            }
        });
        
        // Subscribe to chart data changes
        unsubscribe = chartData.subscribe(data => {
            if (!chart) return;
            
            chart.data.labels = data.labels;
            chart.data.datasets = data.datasets;
            
            chart.options = {
                ...chart.options,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { 
                            color: '#fff',
                            callback: (value: any) => `${value} ${data.unit}`
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
                            label: (context: any) => `${context.dataset.label}: ${formatBytes(context.raw * data.divisor)}`
                        }
                    }
                }
            };
            
            chart.update('none');
        });
    });
    
    onDestroy(() => {
        if (unsubscribe) unsubscribe();
        if (chart) chart.destroy();
    });
</script>

<div class="w-full h-32">
    <canvas bind:this={chartElement}></canvas>
</div> 