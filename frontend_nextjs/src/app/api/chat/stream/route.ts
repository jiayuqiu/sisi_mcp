import { NextRequest } from "next/server";

const DIFY_API_KEY = process.env.DIFY_API_KEY ?? "";
const DIFY_CHATFLOW_URL =
  process.env.DIFY_CHATFLOW_URL ?? "https://api.dify.ai/v1";

export async function POST(req: NextRequest) {
  if (!DIFY_API_KEY) {
    return new Response(
      `data: ${JSON.stringify({ event: "error", message: "DIFY_API_KEY not configured" })}\n\n`,
      { status: 500, headers: { "Content-Type": "text/event-stream" } }
    );
  }

  const body = await req.json();
  const { message, conversation_id } = body as {
    message: string;
    conversation_id?: string;
  };

  const difyRes = await fetch(`${DIFY_CHATFLOW_URL}/chat-messages`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${DIFY_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      inputs: {},
      query: message,
      response_mode: "streaming",
      conversation_id: conversation_id ?? "",
      user: "web-user",
    }),
  });

  if (!difyRes.ok || !difyRes.body) {
    const text = await difyRes.text().catch(() => "Unknown error");
    return new Response(
      `data: ${JSON.stringify({ event: "error", message: text })}\n\n`,
      { status: difyRes.status, headers: { "Content-Type": "text/event-stream" } }
    );
  }

  // Stream the Dify SSE response through to the client
  return new Response(difyRes.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
