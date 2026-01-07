const API_URL = "http://localhost:8000";
const API_KEY = "secret-key"; // Should match backend .env API_KEY

// Stream message and yield tokens in real-time
export async function* streamMessage(message: string) {
    const response = await fetch(`${API_URL}/chat/stream`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
        body: JSON.stringify({ user_input: message, source: "web" }),
    });

    if (!response.ok) {
        throw new Error(`Failed to stream message: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    if (!reader) {
        throw new Error("No response body");
    }

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split("\n");

            for (const line of lines) {
                if (line.trim()) {
                    yield line.trim();
                }
            }
        }
    } finally {
        reader.releaseLock();
    }
}

// Legacy non-streaming version for compatibility
export async function sendMessage(message: string) {
    let fullResponse = "";

    for await (const chunk of streamMessage(message)) {
        // Parse "TOKEN: <text>" format
        if (chunk.startsWith("TOKEN: ")) {
            fullResponse += chunk.substring(7);
        }
    }

    return { answer: fullResponse };
}

export async function saveMemory(text: string) {
    const response = await fetch(`${API_URL}/ingest/web`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
        body: JSON.stringify({ user_input: text, source: "web" }),
    });

    if (!response.ok) throw new Error("Failed to save memory");

    const data = await response.json();
    return { nodes: [], ...data }; // Compatible with existing code
}

export async function fetchGraph() {
    const response = await fetch(`${API_URL}/graph/data`, {
        headers: {
            "X-API-Key": API_KEY,
        },
    });

    if (!response.ok) throw new Error("Failed to fetch graph");
    return response.json();
}

export async function checkHealth() {
    try {
        const response = await fetch(`${API_URL}/health`);
        if (!response.ok) return { status: "offline", database: "UNKNOWN" };
        return response.json();
    } catch (error) {
        return { status: "offline", database: "UNKNOWN" };
    }
}
