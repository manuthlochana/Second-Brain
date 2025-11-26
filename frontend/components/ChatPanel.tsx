"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Database, MessageSquare } from "lucide-react";
import { motion } from "framer-motion";
import { sendMessage, saveMemory } from "../lib/api";

type Message = {
    role: "user" | "assistant";
    content: string;
};

interface ChatPanelProps {
    onInsertSuccess?: () => void;
}

export default function ChatPanel({ onInsertSuccess }: ChatPanelProps) {
    const [mode, setMode] = useState<"query" | "insert">("query");
    const [input, setInput] = useState("");
    const [messages, setMessages] = useState<Message[]>([]);
    const [loading, setLoading] = useState(false);
    const STORAGE_KEY = 'second_brain_chat_history';
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    // Load messages from localStorage on mount
    useEffect(() => {
        const savedMessages = localStorage.getItem(STORAGE_KEY);
        if (savedMessages) {
            try {
                setMessages(JSON.parse(savedMessages));
            } catch (e) {
                console.error("Failed to parse chat history", e);
            }
        }
    }, []);

    // Save messages to localStorage whenever they change
    useEffect(() => {
        if (messages.length > 0) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
        }
    }, [messages]);

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim()) return;

        const userMsg = input;
        setInput("");
        setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
        setLoading(true);

        try {
            let response;
            if (mode === "query") {
                const data = await sendMessage(userMsg);
                response = data.answer;
            } else {
                const data = await saveMemory(userMsg);
                response = `Saved! Extracted ${data.nodes.length} entities.`;
                if (onInsertSuccess) onInsertSuccess();
            }

            setMessages((prev) => [...prev, { role: "assistant", content: response }]);
        } catch (error) {
            setMessages((prev) => [
                ...prev,
                { role: "assistant", content: "❌ Error processing request." },
            ]);
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    return (
        // MAIN CONTAINER: Fixed height, Flex Column
        <div className="flex flex-col h-full bg-slate-900 border-r border-white/10 overflow-hidden">
            {/* 1. HEADER: Fixed Size (flex-none) */}
            <div className="flex-none p-4 border-b border-white/10 flex items-center justify-between bg-slate-900 z-10">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <span className="text-accent">●</span> Second Brain
                </h2>
                <div className="flex bg-slate-800 p-1 rounded-lg">
                    <button
                        onClick={() => setMode("query")}
                        className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${mode === "query"
                            ? "bg-accent text-white shadow-lg"
                            : "text-slate-400 hover:text-white"
                            }`}
                    >
                        <MessageSquare size={14} /> Chat
                    </button>
                    <button
                        onClick={() => setMode("insert")}
                        className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${mode === "insert"
                            ? "bg-emerald-600 text-white shadow-lg"
                            : "text-slate-400 hover:text-white"
                            }`}
                    >
                        <Database size={14} /> Insert
                    </button>
                </div>
            </div>

            {/* 2. MESSAGES AREA: Flexible (flex-1) & Scrollable */}
            <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
                {messages.length === 0 && (
                    <div className="text-center text-slate-500 mt-10">
                        <p>Select a mode and start interacting with your Second Brain.</p>
                    </div>
                )}
                {messages.map((msg, idx) => (
                    <motion.div
                        key={idx}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                        <div
                            className={`max-w-[85%] p-3 rounded-2xl text-sm leading-relaxed ${msg.role === "user"
                                ? "bg-accent text-white rounded-br-none"
                                : "bg-slate-800 text-slate-200 rounded-bl-none"
                                }`}
                        >
                            {msg.content}
                        </div>
                    </motion.div>
                ))}
                {loading && (
                    <div className="flex justify-start">
                        <div className="bg-slate-800 text-slate-400 p-3 rounded-2xl rounded-bl-none text-sm animate-pulse">
                            Thinking...
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* 3. INPUT AREA: Fixed Size (flex-none) */}
            <div className="flex-none p-4 border-t border-white/10 bg-slate-900 z-10">
                <form onSubmit={handleSubmit} className="relative">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={mode === "query" ? "Ask something..." : "Save a memory..."}
                        className="w-full bg-slate-950 text-white placeholder-slate-500 rounded-xl py-3 pl-4 pr-12 focus:outline-none focus:ring-2 focus:ring-accent/50 border border-slate-800"
                    />
                    <button
                        type="submit"
                        disabled={!input.trim() || loading}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-accent text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        <Send size={18} />
                    </button>
                </form>
            </div>
        </div>
    );
}
