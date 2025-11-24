"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import dynamic from "next/dynamic";
import { fetchGraph } from "../lib/api";

// Dynamic import to avoid SSR issues with canvas
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
    ssr: false,
    loading: () => (
        <div className="flex items-center justify-center h-full text-slate-500">
            Loading Graph Engine...
        </div>
    ),
});

const NODE_COLORS = ['#FF5733', '#33FF57', '#3357FF', '#FF33A8', '#A833FF', '#33FFF5', '#FFC300'];

export default function GraphCanvas({ refreshKey }: { refreshKey: number }) {
    const [graphData, setGraphData] = useState({ nodes: [], links: [] });
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState("");
    const containerRef = useRef<HTMLDivElement>(null);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

    const loadGraph = useCallback(async () => {
        console.log("Fetching Graph Data...");
        try {
            const data = await fetchGraph();

            if (!data.nodes || data.nodes.length === 0) {
                console.log("No nodes found in graph data.");
            }

            // Assign colors to nodes
            const coloredNodes = data.nodes.map((node: any, index: number) => ({
                ...node,
                color: NODE_COLORS[index % NODE_COLORS.length]
            }));

            setGraphData({ ...data, nodes: coloredNodes });
        } catch (error) {
            console.error("Failed to load graph:", error);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadGraph();
    }, [loadGraph, refreshKey]);

    useEffect(() => {
        // Handle Resize
        const handleResize = () => {
            if (containerRef.current) {
                setDimensions({
                    width: containerRef.current.clientWidth,
                    height: containerRef.current.clientHeight,
                });
            }
        };

        window.addEventListener("resize", handleResize);
        handleResize(); // Initial size

        return () => window.removeEventListener("resize", handleResize);
    }, []);

    return (
        <div ref={containerRef} className="w-full h-full bg-bg-dark relative overflow-hidden">
            {/* Search Bar */}
            <div className="absolute top-4 left-4 z-20">
                <input
                    type="text"
                    placeholder="🔍 Find Node..."
                    className="bg-slate-900/80 text-white p-2 rounded-lg border border-slate-700 backdrop-blur-sm focus:outline-none focus:border-accent text-sm w-48"
                    onChange={(e) => setSearchTerm(e.target.value)}
                />
            </div>

            {loading && (
                <div className="absolute inset-0 flex items-center justify-center z-10 bg-bg-dark/80 backdrop-blur-sm">
                    <div className="text-accent animate-pulse font-mono">
                        Initializing Neural Link...
                    </div>
                </div>
            )}

            {!loading && (
                <ForceGraph2D
                    width={dimensions.width}
                    height={dimensions.height}
                    graphData={graphData}
                    nodeLabel="name"
                    nodeColor="color"
                    nodeRelSize={6}
                    linkColor={() => "#1e293b"} // Slate 800
                    linkDirectionalArrowLength={3.5}
                    linkDirectionalArrowRelPos={1}
                    backgroundColor="#0f172a" // Bg Dark
                    d3VelocityDecay={0.1}
                    cooldownTicks={100}
                    onEngineStop={() => console.log("Graph stabilized")}
                    nodeCanvasObject={(node: any, ctx, globalScale) => {
                        const label = node.name || node.id;
                        const fontSize = 12 / globalScale;
                        ctx.font = `${fontSize}px Sans-Serif`;

                        // Check for Search Match
                        const isMatch = searchTerm && label.toLowerCase().includes(searchTerm.toLowerCase());

                        if (isMatch) {
                            // Draw Neon Green Ring
                            ctx.beginPath();
                            ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI, false);
                            ctx.strokeStyle = '#39ff14'; // Neon Green
                            ctx.lineWidth = 2 / globalScale;
                            ctx.stroke();
                        }

                        // --- SPECIAL LOGIC FOR ROOT USER ---
                        if (label === "Manuth") {
                            // Draw RECTANGLE for Manuth
                            ctx.fillStyle = '#FFD700'; // Gold Color
                            ctx.fillRect(node.x - 12, node.y - 8, 24, 16); // Draw Box

                            // Label Styling
                            ctx.textAlign = 'center';
                            ctx.textBaseline = 'middle';
                            ctx.fillStyle = 'black'; // Black text on Gold
                            ctx.fillText(label, node.x, node.y);
                        }
                        // --- LOGIC FOR OTHER NODES (Circles) ---
                        else {
                            // Draw CIRCLE
                            ctx.beginPath();
                            ctx.arc(node.x, node.y, 5, 0, 2 * Math.PI, false);
                            ctx.fillStyle = node.color || '#3b82f6';
                            ctx.fill();

                            // Label Styling (Below the node)
                            ctx.textAlign = 'center';
                            ctx.textBaseline = 'top';
                            ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
                            ctx.fillText(label, node.x, node.y + 7);
                        }
                    }}
                />
            )}

            {/* Overlay UI */}
            <div className="absolute top-4 right-4 bg-card-dark/80 backdrop-blur p-3 rounded-lg border border-slate-800 text-xs text-slate-400">
                <div className="flex items-center gap-2 mb-1">
                    <div className="w-2 h-2 rounded-full bg-accent"></div>
                    <span>Nodes: {graphData.nodes.length}</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-slate-600"></div>
                    <span>Connections: {graphData.links.length}</span>
                </div>
            </div>
        </div>
    );
}
