"use client";

import { useState, useRef, useEffect } from "react";
import { Database, MessageSquare } from "lucide-react";
import { motion } from "framer-motion";
import { sendMessage, saveMemory } from "../lib/api";
import ChatInput from "./ChatInput";

type Message = {
    role: "user" | "assistant";
    content: string;
};

interface ChatPanelProps {
    onInsertSuccess?: () => void;
}

export default function ChatPanel({ onInsertSuccess }: ChatPanelProps) {
    const [mode, setMode] = useState<"query" | "insert">("query");
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

    const handleSendMessage = async (text: string) => {
        const userMsg = text;
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
        // FIX 1: Change to Grid Layout (Fixed Header/Input, Flexible Middle)
        <div className="flex flex-col h-full w-full bg-slate-950 overflow-hidden">
            {/* HEADER: Rigid, Fixed Height */}
            <div className="h-16 bg-slate-900 border-b border-slate-800 flex items-center justify-between px-4 z-20 shadow-md">
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

            {/* MESSAGES: Use calc() for definitive height: 100% - (h-16 Header) - (h-20 Input) = 100% - 144px */}
            <div
                className="overflow-y-auto p-4 space-y-4 scroll-smooth"
                style={{ height: 'calc(100% - 144px)' }}
            >
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

            {/* INPUT: Input component call */}
            <ChatInput
                onSendMessage={handleSendMessage}
                loading={loading}
                mode={mode}
            />
        </div>
    );
}
