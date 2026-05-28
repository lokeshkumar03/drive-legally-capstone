const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export async function verifyChallan(payload) {
  const formData = new FormData();
  Object.entries(payload).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") formData.append(key, value);
  });
  const res = await fetch(`${API_BASE_URL}/verify-challan`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function askLegalQuestion(payload) {
  const formData = new FormData();
  Object.entries(payload).forEach(([key, value]) => formData.append(key, value ?? ""));
  const res = await fetch(`${API_BASE_URL}/ask-legal-question`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function reportUrl(path) {
  if (!path) return "#";
  return `${API_BASE_URL}${path}`;
}
