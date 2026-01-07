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
    const [brainState, setBrainState] = useState("Idle");
    const [health, setHealth] = useState("checking");

    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Auto-scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, brainState]);

    // Health Check Polling
    useEffect(() => {
        const checkHealth = async () => {
            try {
                const res = await fetch("http://localhost:8000/health");
                const data = await res.json();
                setHealth(data.database === "DB_CONNECTED" ? "online" : "offline");
            } catch (e) {
                setHealth("offline");
            }
        };

        checkHealth();
        const interval = setInterval(checkHealth, 30000);
        return () => clearInterval(interval);
    }, []);

    const sendMessage = async () => {
        if (!input.trim()) return;

        // Add User Message
        const text = input;
        setInput("");
        setMessages(prev => [...prev, { id: Date.now().toString(), sender: "user", text }]);

        setBrainState("Thinking...");

        // Create placeholder for AI response
        const aiMsgId = Date.now().toString() + "_ai";
        setMessages(prev => [...prev, { id: aiMsgId, sender: "ai", text: "" }]);

        try {
            const response = await fetch("http://localhost:8000/chat/stream", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": "secret-key"
                },
                body: JSON.stringify({ user_input: text })
            });

            if (!response.body) throw new Error("No stream");

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            let fullResponse = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split("\n");

                for (const line of lines) {
                    if (!line) continue;

                    if (line.startsWith("THINKING:")) {
                        setBrainState(line.replace("THINKING:", "").trim());
                    } else if (line.startsWith("TOKEN:")) {
                        setBrainState("Responding...");
                        const token = line.replace("TOKEN:", "");
                        fullResponse += token;

                        // Update the last message (AI placeholder)
                        setMessages(prev => prev.map(msg =>
                            msg.id === aiMsgId ? { ...msg, text: fullResponse } : msg
                        ));
                    }
                }
            }

            setBrainState("Idle");

        } catch (e) {
            setBrainState("Error");
            setMessages(prev => [...prev, { id: Date.now().toString(), sender: "ai", text: "Connection Failed." }]);
        }
    };

    return (
        <div className="flex flex-col h-full bg-slate-950 border-l border-slate-800">
            {/* Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
                <h2 className="font-semibold text-slate-200">Jarvis</h2>
                <div className="flex items-center space-x-4 text-xs">
                    <div className="flex items-center space-x-2">
                        <span className={`w-2 h-2 rounded-full ${health === 'online' ? 'bg-emerald-500' : 'bg-red-500'}`} />
                        <span className="text-slate-500">{health === 'online' ? 'Connected' : 'Local Mode'}</span>
                    </div>

                    <div className="flex items-center space-x-2">
                        <Cpu size={14} className={brainState !== "Idle" ? "animate-pulse text-sky-400" : "text-slate-600"} />
                        <span className={brainState !== "Idle" ? "text-sky-400" : "text-slate-600"}>{brainState}</span>
                    </div>
                </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map((msg) => (
                    <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div className={`max-w-[80%] rounded-lg p-3 text-sm whitespace-pre-wrap ${msg.sender === 'user'
                                ? 'bg-sky-600 text-white'
                                : 'bg-slate-800 text-slate-200 border border-slate-700'
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
                        onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
                        className="p-2 bg-sky-600 hover:bg-sky-500 rounded-lg text-white transition-colors"
                    >
                        <Send size={18} />
                    </button>
                </div>
            </div>
        </div>
    );
}
