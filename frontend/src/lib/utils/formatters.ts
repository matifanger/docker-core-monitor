/**
 * Format bytes to human readable format
 */
export function formatBytes(bytes: number): string {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

/**
 * Format seconds to human readable time format
 */
export function formatTime(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h}h ${m}m ${s}s`;
}

/**
 * Format CPU information for display
 */
export function formatCpuInfo(cpuPercent: number, cpuCount?: number | null, cpuLimit?: number | null): string {
    let result = `${cpuPercent.toFixed(2)}%`;
    if (cpuLimit) {
        result += ` / ${cpuLimit.toFixed(1)} CPUs`;
    } else if (cpuCount) {
        result += ` (${cpuCount} CPUs)`;
    }
    return result;
}

/**
 * Normalize CPU percentage
 * Note: Currently returns the percentage as-is without normalization
 */
export function normalizeCpuPercent(percent: number): number {
    // Return percentage as is without limiting
    return percent;
}

/**
 * Get appropriate unit for network chart values
 */
export function getNetworkChartUnit(values: number[]): { divisor: number, unit: string } {
    const max = Math.max(...values, 1); // Avoid division by zero
    
    if (max >= 1e12) return { divisor: 1e12, unit: 'TB' };
    if (max >= 1e9) return { divisor: 1e9, unit: 'GB' };
    if (max >= 1e6) return { divisor: 1e6, unit: 'MB' };
    if (max >= 1e3) return { divisor: 1e3, unit: 'KB' };
    return { divisor: 1, unit: 'B' };
} 