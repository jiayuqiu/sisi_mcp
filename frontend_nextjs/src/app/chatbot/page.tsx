"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Bot, User, Anchor } from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

const SUGGESTED = [
  "2024年1月马六甲海峡是否发生了异常？",
  "2023年12月曼德海峡为什么发生异常？",
  "2024年3月曼德海峡有没有拥堵？",
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function uid() {
  return Math.random().toString(36).slice(2);
}

function nl2br(text: string) {
  return text.split("\n").map((line, i) => (
    <span key={i}>
      {line}
      {i < text.split("\n").length - 1 && <br />}
    </span>
  ));
}

function pickWorkflowOutputText(outputs: unknown): string {
  if (!outputs || typeof outputs !== "object") return "";
  const obj = outputs as Record<string, unknown>;

  const preferredKeys = ["answer", "formatted_output", "reason", "text", "output"];
  for (const key of preferredKeys) {
    const value = obj[key];
    if (typeof value === "string" && value.trim()) return value;
  }

  for (const value of Object.values(obj)) {
    if (typeof value === "string" && value.trim()) return value;
  }

  return "";
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex gap-2 items-center px-1 py-1">
      <span className="text-xs text-teal-400/70">思考中</span>
      <div className="flex gap-1 items-center">
        <div className="typing-dot" />
        <div className="typing-dot" />
        <div className="typing-dot" />
      </div>
    </div>
  );
}

function ChatBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div
      className={cn(
        "flex gap-3 animate-slide-up",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold",
          isUser
            ? "bg-accent/20 border border-accent/40 text-accent"
            : "bg-teal-500/20 border border-teal-500/40 text-teal-400",
          !isUser && msg.streaming && "avatar-pulse"
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-accent text-white rounded-tr-sm"
            : "bg-navy-700 border border-navy-600 text-slate-200 rounded-tl-sm"
        )}
      >
        {msg.streaming && <TypingIndicator />}
        {msg.content !== "" && (
          <span className={cn("prose-chat", msg.streaming && "mt-1 block")}>{nl2br(msg.content)}</span>
        )}
        {msg.streaming && msg.content !== "" && (
          <span className="inline-block w-0.5 h-4 bg-teal-400 ml-0.5 animate-pulse align-middle" />
        )}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const WELCOME_MESSAGE: Message = {
  id: "welcome",
  role: "assistant",
  content:
    "你好！我是航运通道异常检测助手。\n\n你可以问我关于马六甲海峡或曼德海峡的交通异常问题，例如某月是否发生了异常，或者异常原因分析。",
};

const STORAGE_KEY_MESSAGES = "chatbot_messages";
const STORAGE_KEY_CONVERSATION = "chatbot_conversation_id";

export default function ChatbotPage() {
  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window === "undefined") return [WELCOME_MESSAGE];
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY_MESSAGES);
      if (saved) {
        const parsed = JSON.parse(saved) as Message[];
        return parsed.map((m) => ({ ...m, streaming: false }));
      }
    } catch {}
    return [WELCOME_MESSAGE];
  });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState(() => {
    if (typeof window === "undefined") return "";
    return sessionStorage.getItem(STORAGE_KEY_CONVERSATION) ?? "";
  });
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Persist messages to sessionStorage
  useEffect(() => {
    if (!loading) {
      sessionStorage.setItem(STORAGE_KEY_MESSAGES, JSON.stringify(messages));
    }
  }, [messages, loading]);

  // Persist conversationId to sessionStorage
  useEffect(() => {
    sessionStorage.setItem(STORAGE_KEY_CONVERSATION, conversationId);
  }, [conversationId]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
  }, [input]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || loading) return;

      const userMsg: Message = { id: uid(), role: "user", content: trimmed };
      const assistantId = uid();
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        streaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput("");
      setLoading(true);

      try {
        const res = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: trimmed, conversation_id: conversationId }),
        });

        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (raw === "[DONE]") continue;

            try {
              const json = JSON.parse(raw);

              // Update conversation_id from first event
              if (json.conversation_id) {
                setConversationId(json.conversation_id);
              }

              // Accumulate streamed answer chunks
              if ((json.event === "message" || json.event === "agent_message") && json.answer) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: m.content + json.answer }
                      : m
                  )
                );
              }

              if (json.event === "workflow_finished") {
                const workflowText = pickWorkflowOutputText(json.data?.outputs);
                if (workflowText) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? { ...m, content: m.content || workflowText }
                        : m
                    )
                  );
                }
              }

              if (json.event === "error") {
                const errorMessage =
                  typeof json.message === "string" && json.message.trim()
                    ? json.message
                    : "请求失败，请检查模型配置或余额。";
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: `⚠️ ${errorMessage}`, streaming: false }
                      : m
                  )
                );
              }

              // message_end — finalise
              if (json.event === "message_end") {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, streaming: false } : m
                  )
                );
              }
            } catch {
              // non-JSON line, ignore
            }
          }
        }

        // Ensure streaming flag is cleared
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false } : m
          )
        );
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: "⚠️ 请求失败，请检查后端服务是否正常运行。",
                  streaming: false,
                }
              : m
          )
        );
      } finally {
        setLoading(false);
      }
    },
    [loading, conversationId]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden max-w-3xl w-full mx-auto px-4 py-4 gap-4">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-4 pr-1">
        {messages.map((msg) => (
          <ChatBubble key={msg.id} msg={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Suggested questions (only when no user messages yet) */}
      {messages.length === 1 && (
        <div className="flex flex-wrap gap-2">
          {SUGGESTED.map((q) => (
            <button
              key={q}
              onClick={() => sendMessage(q)}
              className="text-xs px-3 py-1.5 rounded-full border border-teal-500/30 text-teal-400 hover:bg-teal-500/10 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="flex-shrink-0 flex items-end gap-3 bg-navy-800 border border-navy-600 rounded-2xl px-4 py-3 focus-within:border-teal-500/50 transition-colors">
        <Anchor className="w-4 h-4 text-slate-500 mb-2 flex-shrink-0" />
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的问题... (Enter 发送，Shift+Enter 换行)"
          rows={1}
          disabled={loading}
          className="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-500 resize-none outline-none leading-relaxed disabled:opacity-50"
          style={{ maxHeight: 120 }}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
          className={cn(
            "flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-150 mb-0.5",
            input.trim() && !loading
              ? "bg-teal-500 hover:bg-teal-400 text-white shadow-lg shadow-teal-500/20"
              : "bg-navy-700 text-slate-600 cursor-not-allowed"
          )}
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
