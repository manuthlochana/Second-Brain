"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useQuery } from "@tanstack/react-query";

// Dynamically import ForceGraph2D to avoid SSR issues
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
    ssr: false,
});

interface GraphData {
    nodes: { id: string; label: string; type: string; val: number }[];
    links: { source: string; target: string; label: string }[];
}

export default function MindMap() {
    const containerRef = useRef<HTMLDivElement>(null);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

    // Fetch graph data from backend
    const { data: graphData } = useQuery<GraphData>({
        queryKey: ["graphData"],
        queryFn: async () => {
            const res = await fetch("http://localhost:8000/graph/data", {
                headers: { "X-API-Key": "secret-key" } // Hardcoded for dev
            });
            if (!res.ok) throw new Error("Network response was not ok");
            return res.json();
        },
        refetchInterval: 30000, // Poll every 30s for updates
    });

    useEffect(() => {
        // Resize observer to auto-fit graph
        if (!containerRef.current) return;

        const resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                setDimensions({
                    width: entry.contentRect.width,
                    height: entry.contentRect.height,
                });
            }
        });

        resizeObserver.observe(containerRef.current);
        return () => resizeObserver.disconnect();
    }, []);

    return (
        <div ref={containerRef} className="w-full h-full bg-slate-950 border border-slate-800 rounded-xl overflow-hidden relative">
            <div className="absolute top-4 left-4 z-10 bg-slate-900/80 p-2 rounded text-slate-400 text-xs backdrop-blur-sm">
                MindMap v1.0 • {graphData?.nodes.length || 0} Nodes
            </div>

            {graphData && (
                <ForceGraph2D
                    width={dimensions.width}
                    height={dimensions.height}
                    graphData={graphData}
                    nodeLabel="label"
                    nodeColor={(node: any) => {
                        if (node.type === 'Person') return '#c084fc'; // Purple
                        if (node.type === 'Project') return '#38bdf8'; // Blue
                        if (node.type === 'Note') return '#94a3b8'; // Gray
                        return '#22c55e'; // Green (default)
                    }}
                    backgroundColor="#020617" // Slate-950
                    linkColor={() => "#1e293b"} // Slate-800
                />
            )}

            {!graphData && (
                <div className="absolute inset-0 flex items-center justify-center text-slate-500">
                    Loading Knowledge Graph...
                </div>
            )}
        </div>
    );
}
