"use client";

import { useState } from "react";
import { Wallet, Link, Shield } from "lucide-react";

export default function VaultPanel() {
    const [activeTab, setActiveTab] = useState("bank");

    return (
        <div className="h-full bg-slate-900 border-l border-slate-800 p-4 flex flex-col">
            <h2 className="text-slate-200 font-semibold mb-4 flex items-center">
                <Shield className="mr-2 text-emerald-500" size={18} />
                Vault & Context
            </h2>

            {/* Tabs */}
            <div className="flex space-x-2 mb-4">
                <button
                    onClick={() => setActiveTab("bank")}
                    className={`px-3 py-1 rounded text-xs flex items-center ${activeTab === 'bank' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                >
                    <Wallet size={12} className="mr-1" /> Finance
                </button>
                <button
                    onClick={() => setActiveTab("links")}
                    className={`px-3 py-1 rounded text-xs flex items-center ${activeTab === 'links' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                >
                    <Link size={12} className="mr-1" /> Links
                </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto">
                {activeTab === "bank" && (
                    <div className="space-y-2 text-sm text-slate-400">
                        <div className="p-2 border border-slate-800 rounded">
                            <div className="text-xs text-slate-500">Bank of Sample</div>
                            <div className="text-white font-mono">$12,450.00</div>
                        </div>
                        <div className="p-2 border border-slate-800 rounded">
                            <div className="text-xs text-slate-500">Crypto Portfolio</div>
                            <div className="text-white font-mono">$4,200.00</div>
                        </div>
                        <div className="mt-4 text-xs italic text-slate-600">
                            * Real data integration pending via /ingest/bank
                        </div>
                    </div>
                )}

                {activeTab === "links" && (
                    <div className="space-y-2 text-sm text-slate-400">
                        <div className="flex items-center justify-between p-2 border border-slate-800 rounded hover:bg-slate-800/50 cursor-pointer">
                            <span>Daraz Wishlist</span>
                            <Link size={12} />
                        </div>
                        <div className="flex items-center justify-between p-2 border border-slate-800 rounded hover:bg-slate-800/50 cursor-pointer">
                            <span>Project Alpha Repo</span>
                            <Link size={12} />
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
