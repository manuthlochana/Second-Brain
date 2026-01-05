"use client";

import { useState, useEffect, useRef } from "react";
import { Send, Cpu } from "lucide-react";

interface Message {
    id: string;
    sender: "user" | "ai";
    text: string;
    isThinking?: boolean;
}

export default function ChatInterface() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [socket, setSocket] = useState<WebSocket | null>(null);
    const [brainState, setBrainState] = useState("Idle");

    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Auto-scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    // WebSocket Connection
    useEffect(() => {
        const ws = new WebSocket("ws://localhost:8000/ws/status");

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status === "THINKING") {
                setBrainState("Thinking...");
            } else if (data.status === "DONE") {
                setBrainState("Idle");
                // Add response if included
                if (data.response) {
                    setMessages(prev => [...prev, { id: Date.now().toString(), sender: "ai", text: data.response }]);
                }
            } else if (data.status === "ERROR") {
                setBrainState("Error");
                setMessages(prev => [...prev, { id: Date.now().toString(), sender: "ai", text: `Error: ${data.message}` }]);
            }
        };

        setSocket(ws);
        return () => ws.close();
    }, []);

    const sendMessage = async () => {
        if (!input.trim()) return;

        // Add User Message
        const text = input;
        setInput("");
        setMessages(prev => [...prev, { id: Date.now().toString(), sender: "user", text }]);

        // Trigger Backend (via HTTP, response updates mostly via WS or we can await simple response)
        // We await the HTTP response to confirm receipts, but the actual "Answer" comes via WS broadcasts logic in main.py? 
        // Actually main.py "process_brain_task" broadcasts the final response too in "DONE".

        try {
            await fetch("http://localhost:8000/ingest/web", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": "secret-key"
                },
                body: JSON.stringify({ user_input: text })
            });
            // We rely on WS for the response
        } catch (e) {
            setMessages(prev => [...prev, { id: Date.now().toString(), sender: "ai", text: "Failed to reach brain." }]);
        }
    };

    return (
        <div className="flex flex-col h-full bg-slate-950 border-l border-slate-800">
            {/* Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
                <h2 className="font-semibold text-slate-200">Jarvis</h2>
                <div className="flex items-center space-x-2 text-xs">
                    <Cpu size={14} className={brainState === "Thinking..." ? "animate-pulse text-sky-400" : "text-slate-600"} />
                    <span className={brainState === "Thinking..." ? "text-sky-400" : "text-slate-600"}>{brainState}</span>
                </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((msg) => (
                    <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[80%] rounded-lg p-3 text-sm ${msg.sender === 'user'
                                ? 'bg-sky-600 text-white'
                                : 'bg-slate-800 text-slate-200'
                            }`}>
                            {msg.text}
                        </div>
                    </div>
                ))}
                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-4 border-t border-slate-800">
                <div className="flex items-center space-x-2">
                    <input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
                        placeholder="Message Brain..."
                        className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-sky-500 transition-colors"
                    />
                    <button
                        onClick={sendMessage}
                        className="p-2 bg-sky-600 hover:bg-sky-500 rounded-lg text-white transition-colors"
                    >
                        <Send size={18} />
                    </button>
                </div>
            </div>
        </div>
    );
}
