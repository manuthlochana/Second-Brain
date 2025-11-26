"use client";

import { useState } from "react";
import { Send } from "lucide-react";

interface ChatInputProps {
    onSendMessage: (text: string) => void;
    loading: boolean;
    mode: "query" | "insert";
}

export default function ChatInput({ onSendMessage, loading, mode }: ChatInputProps) {
    const [input, setInput] = useState("");

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || loading) return;
        onSendMessage(input);
        setInput("");
    };

    return (
        <div className="h-20 bg-slate-900 border-t border-slate-800 p-4 z-20">
            <form onSubmit={handleSubmit} className="relative h-full flex items-center">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder={mode === "query" ? "Ask something..." : "Save a memory..."}
                    className="w-full h-12 bg-slate-950 text-white placeholder-slate-500 rounded-xl pl-4 pr-12 focus:outline-none focus:ring-2 focus:ring-accent/50 border border-slate-800 transition-all"
                    disabled={loading}
                />
                <button
                    type="submit"
                    disabled={!input.trim() || loading}
                    className="absolute right-2 p-2 bg-accent text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    <Send size={18} />
                </button>
            </form>
        </div>
    );
}
