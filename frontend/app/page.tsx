"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MindMap from "@/components/MindMap";
import ChatInterface from "@/components/ChatInterface";
import VaultPanel from "@/components/VaultPanel";
// Mock simple Toast for now to avoid installing shadcn full setup heavily if not needed for demo
// But for "High end", we should assume Toaster is present. I will add a simple placeholder toaster.

const queryClient = new QueryClient();

export default function Home() {
  return (
    <QueryClientProvider client={queryClient}>
      <main className="flex h-screen bg-black text-slate-200 overflow-hidden">
        {/* Mindmap Area (Center) */}
        <section className="flex-1 p-4 relative">
          <MindMap />
          {/* Proactive Alert Overlay (Mock) */}
          <div className="absolute top-4 right-4 pointer-events-none">
            {/* Toasts would appear here */}
          </div>
        </section>

        {/* Sidebar (Right) */}
        <aside className="w-[400px] flex flex-col border-l border-slate-800">
          <div className="h-1/2 border-b border-slate-800">
            <ChatInterface />
          </div>
          <div className="h-1/2">
            <VaultPanel />
          </div>
        </aside>
      </main>
    </QueryClientProvider>
  );
}
