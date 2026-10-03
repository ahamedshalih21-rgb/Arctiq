/**
 * Gemini AI Service for Arctiq Cold Storage Assistant
 * ----------------------------------------------------
 * Connects to Google Gemini API to answer farmer questions about
 * spoilage prediction, energy savings, maintenance, and marketplace recovery.
 */

export async function askGemini(userMessage) {
  const apiKey = import.meta.env.VITE_GEMINI_API_KEY;

  if (!apiKey || apiKey === 'your_actual_api_key_here') {
    console.warn('Gemini API key not configured. Set VITE_GEMINI_API_KEY in frontend/.env.local');
    return 'Gemini API key not configured. Please add your VITE_GEMINI_API_KEY in frontend/.env.local to enable live AI assistance.';
  }

  const systemPrompt = `You are Arctiq Assistant, an AI expert in cold-storage energy optimization and spoilage prediction for small-scale Indian farmers.

Your role:
- Answer questions about spoilage prediction (shelf life, risk levels, LSTM model)
- Explain energy savings (duty cycle, power consumption, cost calculations)
- Provide maintenance tips (compressor health, Arrhenius degradation, alert thresholds)
- Advise on Recovery Exchange marketplace (selling at-risk produce, buyers nearby)
- Always mention ₹8/kWh as default rate but remind users their rate may differ by state
- Keep responses under 150 words, clear and actionable for farmers with basic literacy
- If asked about non-Arctiq topics, politely redirect: "I specialize in cold storage and energy. Ask me about your Arctiq system!"

Always respond in simple, farmer-friendly language. Use examples. Provide next steps.`;

  const requestBody = JSON.stringify({
    contents: [
      {
        parts: [
          { text: systemPrompt },
          { text: userMessage }
        ]
      }
    ]
  });

  // Endpoints to try in order (gemini-1.5-flash and gemini-pro)
  const endpoints = [
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`,
    `https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key=${apiKey}`,
  ];

  for (const url of endpoints) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: requestBody,
      });

      if (response.ok) {
        const data = await response.json();
        const assistantMessage = data.candidates?.[0]?.content?.parts?.[0]?.text;
        if (assistantMessage) {
          return assistantMessage.trim();
        }
      } else {
        console.warn(`Gemini endpoint ${url.split('?')[0]} returned ${response.status}`);
      }
    } catch (err) {
      console.warn(`Gemini fetch attempt error:`, err);
    }
  }

  return "Sorry, I couldn't process your question right now. Please check your network connection and try again.";
}
