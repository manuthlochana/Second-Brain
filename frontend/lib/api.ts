const API_URL = "http://localhost:8002";

export async function sendMessage(message: string) {
    const response = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
    });
    if (!response.ok) throw new Error("Failed to send message");
    return response.json();
}

export async function saveMemory(text: string) {
    const response = await fetch(`${API_URL}/insert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
    });
    if (!response.ok) throw new Error("Failed to save memory");
    return response.json();
}

export async function fetchGraph() {
    const response = await fetch(`${API_URL}/graph`);
    if (!response.ok) throw new Error("Failed to fetch graph");
    return response.json();
}
