import React, { useState, useRef, useEffect } from 'react'
import './ChatInterface.css'

interface Message {
  id: string
  type: 'user' | 'bot' | 'system'
  text: string
  timestamp: Date
  action?: string
  requiresConfirmation?: boolean
}

interface Props {
  onSendCommand: (text: string) => void
}

export const ChatInterface: React.FC<Props> = ({ onSendCommand }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '0',
      type: 'system',
      text: 'Chat with your trading bot. Try commands like: "sell AAPL at $150", "close position", "what\'s the latest news?"',
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return

    // Add user message
    const userMsg: Message = {
      id: Date.now().toString(),
      type: 'user',
      text: input,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    // Send command to backend
    try {
      onSendCommand(input)

      // Simulate bot response (replace with actual API response)
      setTimeout(() => {
        const botMsg: Message = {
          id: (Date.now() + 1).toString(),
          type: 'bot',
          text: 'Command received and validated. Ready to execute on your confirmation.',
          timestamp: new Date(),
          action: 'READY_TO_EXECUTE',
          requiresConfirmation: true,
        }
        setMessages((prev) => [...prev, botMsg])
        setIsLoading(false)
      }, 500)
    } catch (error) {
      console.error('Error sending command:', error)
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        type: 'system',
        text: 'Failed to process command. Please try again.',
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, errorMsg])
      setIsLoading(false)
    }
  }

  const handleConfirmAction = (msgId: string) => {
    const msg = messages.find((m) => m.id === msgId)
    if (msg) {
      const confirmMsg: Message = {
        id: (Date.now() + 1).toString(),
        type: 'system',
        text: '✓ Action confirmed and executed!',
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, confirmMsg])
    }
  }

  return (
    <div className="chat-interface">
      <h3>Trade Commands</h3>
      
      <div className="chat-messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message message-${msg.type}`}>
            <div className="message-content">
              <p>{msg.text}</p>
              {msg.requiresConfirmation && (
                <div className="message-actions">
                  <button
                    className="btn btn-small btn-success"
                    onClick={() => handleConfirmAction(msg.id)}
                  >
                    Confirm
                  </button>
                  <button className="btn btn-small btn-secondary">Cancel</button>
                </div>
              )}
            </div>
            <span className="message-time">{msg.timestamp.toLocaleTimeString()}</span>
          </div>
        ))}
        {isLoading && (
          <div className="message message-bot">
            <span className="typing-indicator">
              <span></span><span></span><span></span>
            </span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSendMessage} className="chat-input-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g., 'sell AAPL at $150' or 'close all positions'"
          disabled={isLoading}
          className="chat-input"
        />
        <button type="submit" disabled={isLoading} className="btn btn-primary">
          Send
        </button>
      </form>

      <div className="quick-commands">
        <p className="label">Quick Commands:</p>
        <div className="command-buttons">
          <button
            className="quick-cmd"
            onClick={() => {
              setInput('Show portfolio summary')
              setTimeout(() => {
                document.querySelector<HTMLFormElement>('.chat-input-form')?.dispatchEvent(
                  new Event('submit', { bubbles: true })
                )
              }, 0)
            }}
          >
            📊 Summary
          </button>
          <button
            className="quick-cmd"
            onClick={() => {
              setInput('Close all positions')
              setTimeout(() => {
                document.querySelector<HTMLFormElement>('.chat-input-form')?.dispatchEvent(
                  new Event('submit', { bubbles: true })
                )
              }, 0)
            }}
          >
            🔴 Close All
          </button>
          <button
            className="quick-cmd"
            onClick={() => {
              setInput('What\'s the latest news?')
              setTimeout(() => {
                document.querySelector<HTMLFormElement>('.chat-input-form')?.dispatchEvent(
                  new Event('submit', { bubbles: true })
                )
              }, 0)
            }}
          >
            📰 News
          </button>
          <button
            className="quick-cmd"
            onClick={() => {
              setInput('Check market conditions')
              setTimeout(() => {
                document.querySelector<HTMLFormElement>('.chat-input-form')?.dispatchEvent(
                  new Event('submit', { bubbles: true })
                )
              }, 0)
            }}
          >
            📈 Market
          </button>
        </div>
      </div>
    </div>
  )
}
