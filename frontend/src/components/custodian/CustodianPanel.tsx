"use client"

import { useEffect, useRef, useState } from "react"
import {
  createCustodianSession,
  endCustodianSession,
  getCustodianMessages,
  listCustodianSessions,
  streamCustodianMessage,
} from "@/lib/api"
import type { CustodianMessage, CustodianSession } from "@/lib/types"

interface DisplayMessage {
  role: CustodianMessage["role"]
  content: string
}

function toDisplay(m: CustodianMessage): DisplayMessage {
  if (m.role === "tool") {
    return { role: "tool", content: `Searched the archive for "${m.toolInput ?? ""}"` }
  }
  return { role: m.role, content: m.content }
}

export function CustodianPanel({ onClose }: { onClose: () => void }) {
  const [sessions, setSessions] = useState<CustodianSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listCustodianSessions().then(setSessions).catch(() => setSessions([]))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // ponytail: history is fetched explicitly (switchTo) rather than via an
  // activeId-keyed effect — an effect would also fire when send()/
  // startNewConversation() set activeId for a brand-new session, racing
  // with and clobbering the optimistic messages just appended below.
  function switchTo(sessionId: string) {
    setActiveId(sessionId)
    getCustodianMessages(sessionId).then((msgs) => setMessages(msgs.map(toDisplay)))
  }

  async function startNewConversation() {
    const created = await createCustodianSession()
    setSessions((prev) => [created, ...prev])
    setActiveId(created.id)
    setMessages([])
  }

  async function send() {
    const content = input.trim()
    if (!content || sending) return
    setError(null)
    let sessionId = activeId
    if (!sessionId) {
      const created = await createCustodianSession()
      setSessions((prev) => [created, ...prev])
      setActiveId(created.id)
      setMessages([])
      sessionId = created.id
    }
    setInput("")
    setMessages((prev) => [...prev, { role: "user", content }])
    setSending(true)
    let assistantSoFar = ""
    setMessages((prev) => [...prev, { role: "assistant", content: "" }])
    await streamCustodianMessage(sessionId, content, {
      onToken(delta) {
        assistantSoFar += delta
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = { role: "assistant", content: assistantSoFar }
          return next
        })
      },
      onToolCall(toolName, query) {
        setMessages((prev) => {
          const next = [...prev]
          next.splice(next.length - 1, 0, {
            role: "tool",
            content: `Searched the archive for "${query}"`,
          })
          return next
        })
      },
      onDone() {
        setSending(false)
      },
      onError(message) {
        setSending(false)
        setError(message)
      },
    })
  }

  async function endActive() {
    if (!activeId) return
    await endCustodianSession(activeId)
    setActiveId(null)
    setMessages([])
  }

  return (
    <div className="fixed bottom-24 right-6 z-50 w-96 h-[32rem] bg-surface border border-hairline rounded-hearth shadow-lg flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-hairline">
        <span className="font-heading text-sm text-ink">Custodian</span>
        <div className="flex items-center gap-2">
          <button
            onClick={startNewConversation}
            className="text-xs font-ui text-muted hover:text-ink"
          >
            New
          </button>
          <button onClick={onClose} aria-label="Close" className="text-xs font-ui text-muted hover:text-ink">
            Close
          </button>
        </div>
      </div>
      {sessions.length > 0 && (
        <div className="flex gap-1 px-4 py-2 border-b border-hairline overflow-x-auto">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => switchTo(s.id)}
              className={[
                "px-2 py-1 rounded-meridian text-xs font-ui whitespace-nowrap",
                s.id === activeId ? "bg-surface-hover text-accent" : "text-muted",
              ].join(" ")}
            >
              {s.title ?? "New conversation"}
            </button>
          ))}
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.role === "tool"
                ? "text-xs text-muted italic"
                : m.role === "user"
                  ? "text-sm text-ink text-right"
                  : "text-sm text-ink"
            }
          >
            {m.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {error && <div className="px-4 py-1 text-xs text-status-failed">{error}</div>}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-hairline">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !sending) send()
          }}
          placeholder="Ask the Custodian..."
          className="flex-1 bg-canvas border border-hairline rounded-meridian px-3 py-1.5 text-sm text-ink outline-none focus:border-accent"
        />
        <button
          onClick={send}
          disabled={sending}
          className="px-3 py-1.5 rounded-meridian bg-accent text-canvas text-xs font-ui disabled:opacity-50"
        >
          Send
        </button>
      </div>
      {activeId && (
        <button onClick={endActive} className="px-4 py-2 text-xs font-ui text-muted hover:text-ink border-t border-hairline">
          End conversation
        </button>
      )}
    </div>
  )
}
