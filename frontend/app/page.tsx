"use client";

import { useState } from "react";
import ChatPanel from "../components/ChatPanel";
import GraphCanvas from "../components/GraphCanvas";

export default function Home() {
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <main className="grid grid-cols-12 h-screen bg-bg-dark text-white overflow-hidden">
      {/* Left Column: Chat Interface */}
      <div className="col-span-4 h-full border-r border-slate-800">
        <ChatPanel />
      </div>

      {/* Right Column: Knowledge Graph */}
      <div className="col-span-8 h-full relative">
        <GraphCanvas refreshKey={refreshKey} />
      </div>
    </main>
  );
}
