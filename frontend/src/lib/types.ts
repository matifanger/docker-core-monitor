// src/lib/types.ts
export interface Container {
    id: string;
    name: string;
    status: string;
}

export interface Stats {
    name: string;
    status: string;
    cpu_percent: number;
    memory_usage: number;
    memory_limit: number;
    network_rx: number;
    network_tx: number;
    io_read: number;
    io_write: number;
    uptime: number;
    cpu_limit?: number | null;
    cpu_shares?: number | null;
}

export interface NetworkHistory {
    rx: number[];
    tx: number[];
}