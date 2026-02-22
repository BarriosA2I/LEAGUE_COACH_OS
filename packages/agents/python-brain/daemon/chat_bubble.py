"""
================================================================================
LEAGUE COACH OS — AI CHAT BUBBLE OVERLAY
================================================================================
A persistent floating AI coach bubble that lives on top of League of Legends.

Two states:
  🔵 BUBBLE (collapsed): Small teal circle in corner of screen
     - Click to expand into chat
     - Pulses/glows when new coaching is available
     - Shows mini-notification badge for unread advice
     - Draggable to any screen position

  💬 CHAT (expanded): Full AI coaching chat panel
     - Chat history with all coaching advice
     - Type questions: "should I build armor pen?" "how do I beat Darius?"
     - Auto-posts coaching from PrintScreen screenshots
     - Quick-action buttons: "Build Path" "Matchup" "Teamfight" "What do I buy?"
     - Scrollable history persists across the entire game
     - Minimize back to bubble

Architecture:
  - Local Flask server (localhost:5050) serves the chat UI
  - pywebview creates a transparent always-on-top frameless window
  - WebSocket for real-time coaching push (no polling)
  - Anthropic API for freeform chat questions
  - Full game session context injected into every chat response

Author: Barrios A2I | Version: 3.0.0
================================================================================
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("league_coach.chat_bubble")


# =============================================================================
# CHAT MESSAGE MODEL
# =============================================================================

@dataclass
class ChatMessage:
    """A single message in the coaching chat."""
    id: str = ""
    role: str = "assistant"          # "user" | "assistant" | "system" | "coaching"
    content: str = ""
    timestamp: float = 0.0
    message_type: str = "text"       # "text" | "build" | "matchup" | "death" | "teamfight" | "notification"

    # Structured coaching data (for rich rendering)
    coaching_data: Optional[Dict] = None

    # Display metadata
    champion_icon: str = ""          # Champion name for avatar
    is_pinned: bool = False
    is_unread: bool = True

    # Monotonic counter for unique IDs
    _id_counter = 0

    def __post_init__(self):
        if not self.id:
            ChatMessage._id_counter += 1
            self.id = f"msg_{int(time.time() * 1000)}_{ChatMessage._id_counter}"
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> Dict:
        d = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "message_type": self.message_type,
            "champion_icon": self.champion_icon,
            "is_pinned": self.is_pinned,
            "is_unread": self.is_unread,
        }
        if self.coaching_data:
            d["coaching_data"] = self.coaching_data
        return d


# =============================================================================
# CHAT SESSION — manages conversation history + context
# =============================================================================

class ChatSession:
    """
    Manages the full chat conversation between the player and the AI coach.

    Combines:
    - Automatic coaching messages (from PrintScreen pipeline)
    - Player questions (typed in chat)
    - Game session context (items, KDA, matchup, etc.)
    """

    def __init__(self, max_history: int = 200):
        self.messages: List[ChatMessage] = []
        self.max_history = max_history
        self.unread_count = 0

        # Game context (injected from LiveCoachingPipeline)
        self.game_context: Dict = {}
        self.user_champion: str = ""
        self.user_role: str = ""
        self.lane_opponent: str = ""
        self.current_build: List[str] = []
        self.game_phase: str = ""

        # Welcome message
        self.add_message(ChatMessage(
            role="system",
            content="⚡ League Coach OS online. I'll analyze your screenshots and answer any questions about your game. Press PrintScreen anytime for coaching!",
            message_type="notification",
        ))

    def add_message(self, msg: ChatMessage) -> ChatMessage:
        """Add a message to the chat history."""
        self.messages.append(msg)
        if msg.role in ("assistant", "coaching"):
            self.unread_count += 1
        if len(self.messages) > self.max_history:
            # Keep pinned messages + trim oldest
            pinned = [m for m in self.messages if m.is_pinned]
            unpinned = [m for m in self.messages if not m.is_pinned]
            self.messages = pinned + unpinned[-(self.max_history - len(pinned)):]
        return msg

    def add_coaching_result(self, result: Any) -> ChatMessage:
        """Convert a CoachingResult into a chat message."""
        # Build rich content from the coaching result
        content_parts = []

        headline = getattr(result, 'headline', '')
        if headline:
            content_parts.append(f"**{headline}**")

        tips = getattr(result, 'next_30_seconds', [])
        if tips:
            content_parts.append("\n🎯 **Do Now:**")
            for i, tip in enumerate(tips[:3], 1):
                content_parts.append(f"  {i}. {tip}")

        buy_now = getattr(result, 'buy_now', [])
        if buy_now:
            content_parts.append("\n🛒 **Buy:**")
            for item in buy_now:
                name = item.get('item', '?')
                gold = item.get('gold', 0)
                reason = item.get('reason', '')
                content_parts.append(f"  → {name} ({gold}g) — {reason}")

        laner = getattr(result, 'laner_name', '')
        if laner and not getattr(result, 'is_botlane', False):
            content_parts.append(f"\n⚔️ **vs {laner}:**")
            trade = getattr(result, 'trade_pattern', '')
            if trade:
                content_parts.append(f"  Trade: {trade}")
            punish = getattr(result, 'punish_when', '')
            if punish:
                content_parts.append(f"  Punish: {punish}")
            avoid = getattr(result, 'avoid', '')
            if avoid:
                content_parts.append(f"  ❌ Avoid: {avoid}")

        if getattr(result, 'is_botlane', False):
            adc = getattr(result, 'enemy_adc', '')
            sup = getattr(result, 'enemy_support', '')
            content_parts.append(f"\n⚔️ **Bot Lane vs {adc} + {sup}:**")
            combo = getattr(result, 'their_kill_combo', '')
            if combo:
                content_parts.append(f"  💀 Kill combo: {combo}")
            win = getattr(result, 'your_win_condition', '')
            if win:
                content_parts.append(f"  ✅ Win con: {win}")

        death = getattr(result, 'death_reason', '')
        if death:
            count = getattr(result, 'death_count', 0)
            content_parts.append(f"\n💀 **Death #{count}:** {death}")
            fix = getattr(result, 'death_fix', '')
            if fix:
                content_parts.append(f"  Fix: {fix}")

        content = "\n".join(content_parts) if content_parts else headline

        # Determine message type from game state
        state = getattr(result, 'game_state', 'unknown')
        msg_type_map = {
            "loading_screen": "matchup",
            "tab_scoreboard": "build",
            "shop_open": "build",
            "in_game_laning": "matchup",
            "death_screen": "death",
            "in_game_teamfight": "teamfight",
            "post_game_stats": "text",
        }

        msg = ChatMessage(
            role="coaching",
            content=content,
            message_type=msg_type_map.get(state, "text"),
            coaching_data=asdict(result) if hasattr(result, '__dataclass_fields__') else {},
            champion_icon=self.user_champion,
        )

        # Update game context
        self.game_phase = getattr(result, 'game_phase', self.game_phase)
        build = getattr(result, 'full_build', [])
        if build:
            self.current_build = build
        laner_name = getattr(result, 'laner_name', '')
        if laner_name:
            self.lane_opponent = laner_name

        return self.add_message(msg)

    def mark_all_read(self):
        """Mark all messages as read."""
        for msg in self.messages:
            msg.is_unread = False
        self.unread_count = 0

    def get_context_prompt(self) -> str:
        """Build context string for the AI to answer freeform questions."""
        parts = [
            "You are an expert League of Legends coach embedded in a live game overlay.",
            "Give SHORT, SPECIFIC, ACTIONABLE answers. No fluff. Like a coach shouting from sideline.",
            "",
            f"Player's champion: {self.user_champion or 'Unknown'}",
            f"Role: {self.user_role or 'Unknown'}",
            f"Lane opponent: {self.lane_opponent or 'Unknown'}",
            f"Game phase: {self.game_phase or 'Unknown'}",
            f"Current build: {', '.join(self.current_build) if self.current_build else 'Unknown'}",
        ]

        if self.game_context:
            parts.append(f"\nFull game context: {json.dumps(self.game_context, indent=None)}")

        # Include last few coaching messages for conversation context
        recent = [m for m in self.messages[-10:] if m.role in ("coaching", "user", "assistant")]
        if recent:
            parts.append("\nRecent conversation:")
            for m in recent[-5:]:
                prefix = "Player" if m.role == "user" else "Coach"
                parts.append(f"  {prefix}: {m.content[:200]}")

        return "\n".join(parts)

    def get_messages_json(self) -> List[Dict]:
        """Get all messages as JSON-serializable list."""
        return [m.to_dict() for m in self.messages]


# =============================================================================
# HTML/CSS/JS — The complete chat bubble UI
# =============================================================================

CHAT_BUBBLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>League Coach OS</title>
<style>
  /* ── Reset ── */
  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg: #0D1117;
    --bg-section: #161B22;
    --bg-highlight: #1C2333;
    --bg-input: #0D1117;
    --teal: #00CED1;
    --teal-dim: rgba(0, 206, 209, 0.15);
    --teal-glow: rgba(0, 206, 209, 0.4);
    --gold: #FFD700;
    --green: #10B981;
    --red: #EF4444;
    --orange: #F59E0B;
    --blue: #3B82F6;
    --purple: #A855F7;
    --white: #E6EDF3;
    --gray: #8B949E;
    --dark-gray: #30363D;
    --font: 'Segoe UI', system-ui, -apple-system, sans-serif;
    --font-mono: 'Consolas', 'Cascadia Code', monospace;
    --radius: 12px;
    --bubble-size: 56px;
  }

  body {
    font-family: var(--font);
    background: transparent;
    color: var(--white);
    overflow: hidden;
    height: 100vh;
    width: 100vw;
    user-select: none;
  }

  /* ══════════════════════════════════════════════
     BUBBLE (collapsed state)
     ══════════════════════════════════════════════ */
  #bubble {
    position: fixed;
    bottom: 80px;
    right: 24px;
    width: var(--bubble-size);
    height: var(--bubble-size);
    border-radius: 50%;
    background: linear-gradient(135deg, #0D1117 0%, #161B22 100%);
    border: 2px solid var(--teal);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 20px rgba(0, 206, 209, 0.3), inset 0 0 20px rgba(0, 206, 209, 0.1);
    z-index: 99999;
  }

  #bubble:hover {
    transform: scale(1.1);
    box-shadow: 0 4px 30px rgba(0, 206, 209, 0.5), inset 0 0 25px rgba(0, 206, 209, 0.15);
    border-color: var(--gold);
  }

  #bubble .icon {
    font-size: 24px;
    filter: drop-shadow(0 0 6px var(--teal));
  }

  #bubble .badge {
    position: absolute;
    top: -4px;
    right: -4px;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: var(--red);
    color: white;
    font-size: 11px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 2px solid var(--bg);
    display: none;
  }

  #bubble .badge.visible { display: flex; }

  #bubble.has-new {
    animation: pulse 2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { box-shadow: 0 4px 20px rgba(0, 206, 209, 0.3); }
    50% { box-shadow: 0 4px 35px rgba(0, 206, 209, 0.7), 0 0 60px rgba(0, 206, 209, 0.2); }
  }

  /* ══════════════════════════════════════════════
     CHAT PANEL (expanded state)
     ══════════════════════════════════════════════ */
  #chat-panel {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 420px;
    height: 600px;
    max-height: 80vh;
    background: var(--bg);
    border: 1px solid var(--dark-gray);
    border-radius: var(--radius);
    display: none;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.6), 0 0 1px rgba(0, 206, 209, 0.3);
    z-index: 99998;
    animation: slideUp 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  }

  #chat-panel.open { display: flex; }

  @keyframes slideUp {
    from { transform: translateY(20px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  /* ── Header ── */
  .chat-header {
    padding: 12px 16px;
    background: linear-gradient(135deg, var(--bg-section) 0%, var(--bg) 100%);
    border-bottom: 1px solid var(--dark-gray);
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: move;
    flex-shrink: 0;
  }

  .chat-header .title {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .chat-header .title .logo { font-size: 18px; }

  .chat-header .title h3 {
    font-size: 14px;
    font-weight: 600;
    color: var(--teal);
    letter-spacing: 0.5px;
  }

  .chat-header .title .status {
    font-size: 11px;
    color: var(--green);
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .chat-header .title .status::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--green);
    display: inline-block;
  }

  .chat-header .controls {
    display: flex;
    gap: 8px;
  }

  .chat-header .controls button {
    background: none;
    border: 1px solid var(--dark-gray);
    color: var(--gray);
    width: 28px;
    height: 28px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }

  .chat-header .controls button:hover {
    border-color: var(--teal);
    color: var(--teal);
    background: var(--teal-dim);
  }

  /* ── Quick Actions Bar ── */
  .quick-actions {
    padding: 8px 12px;
    display: flex;
    gap: 6px;
    overflow-x: auto;
    border-bottom: 1px solid var(--dark-gray);
    flex-shrink: 0;
    background: var(--bg-section);
  }

  .quick-actions::-webkit-scrollbar { height: 0; }

  .quick-btn {
    padding: 5px 12px;
    border-radius: 16px;
    border: 1px solid var(--dark-gray);
    background: var(--bg);
    color: var(--gray);
    font-size: 12px;
    white-space: nowrap;
    cursor: pointer;
    transition: all 0.15s;
    font-family: var(--font);
  }

  .quick-btn:hover {
    border-color: var(--teal);
    color: var(--teal);
    background: var(--teal-dim);
  }

  .quick-btn .emoji { margin-right: 4px; }

  /* ── Messages Area ── */
  #messages {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    scroll-behavior: smooth;
  }

  #messages::-webkit-scrollbar { width: 4px; }
  #messages::-webkit-scrollbar-thumb { background: var(--dark-gray); border-radius: 4px; }
  #messages::-webkit-scrollbar-track { background: transparent; }

  /* ── Message Bubbles ── */
  .message {
    max-width: 92%;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 13px;
    line-height: 1.5;
    animation: fadeIn 0.2s ease;
    word-wrap: break-word;
  }

  @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

  .message.user {
    align-self: flex-end;
    background: linear-gradient(135deg, var(--teal) 0%, #00A5A8 100%);
    color: #0D1117;
    border-bottom-right-radius: 4px;
    font-weight: 500;
  }

  .message.assistant, .message.coaching {
    align-self: flex-start;
    background: var(--bg-section);
    border: 1px solid var(--dark-gray);
    border-bottom-left-radius: 4px;
  }

  .message.system {
    align-self: center;
    background: var(--teal-dim);
    border: 1px solid rgba(0, 206, 209, 0.2);
    color: var(--teal);
    font-size: 12px;
    text-align: center;
    max-width: 100%;
  }

  .message.notification {
    align-self: center;
    background: var(--bg-highlight);
    border: 1px solid var(--dark-gray);
    color: var(--gray);
    font-size: 12px;
    text-align: center;
    max-width: 100%;
    padding: 6px 12px;
  }

  /* ── Message type badges ── */
  .message .type-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 6px;
  }

  .type-badge.build { background: rgba(255, 215, 0, 0.15); color: var(--gold); }
  .type-badge.matchup { background: rgba(239, 68, 68, 0.15); color: var(--red); }
  .type-badge.death { background: rgba(239, 68, 68, 0.2); color: var(--red); }
  .type-badge.teamfight { background: rgba(168, 85, 247, 0.15); color: var(--purple); }

  /* ── Formatted content inside messages ── */
  .message .content strong, .message .content b {
    color: var(--gold);
    font-weight: 600;
  }

  .message.coaching .content { white-space: pre-line; }

  .message .timestamp {
    font-size: 10px;
    color: var(--gray);
    opacity: 0.6;
    margin-top: 4px;
  }

  /* ── Typing indicator ── */
  .typing-indicator {
    align-self: flex-start;
    padding: 8px 14px;
    background: var(--bg-section);
    border: 1px solid var(--dark-gray);
    border-radius: 12px;
    display: none;
  }

  .typing-indicator.visible { display: flex; gap: 4px; align-items: center; }

  .typing-indicator .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--teal);
    animation: typingBounce 1.2s infinite;
  }

  .typing-indicator .dot:nth-child(2) { animation-delay: 0.15s; }
  .typing-indicator .dot:nth-child(3) { animation-delay: 0.3s; }

  @keyframes typingBounce {
    0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
    40% { transform: translateY(-6px); opacity: 1; }
  }

  /* ── Input Area ── */
  .chat-input-area {
    padding: 10px 12px;
    border-top: 1px solid var(--dark-gray);
    background: var(--bg-section);
    display: flex;
    gap: 8px;
    align-items: flex-end;
    flex-shrink: 0;
  }

  .chat-input-area textarea {
    flex: 1;
    padding: 8px 12px;
    background: var(--bg-input);
    border: 1px solid var(--dark-gray);
    border-radius: 10px;
    color: var(--white);
    font-family: var(--font);
    font-size: 13px;
    resize: none;
    outline: none;
    min-height: 38px;
    max-height: 100px;
    line-height: 1.4;
    transition: border-color 0.15s;
  }

  .chat-input-area textarea:focus {
    border-color: var(--teal);
  }

  .chat-input-area textarea::placeholder {
    color: var(--gray);
    opacity: 0.6;
  }

  .send-btn {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    border: none;
    background: var(--teal);
    color: var(--bg);
    cursor: pointer;
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
    flex-shrink: 0;
  }

  .send-btn:hover { background: var(--gold); transform: scale(1.05); }
  .send-btn:active { transform: scale(0.95); }

  /* ── Game context bar ── */
  .game-context {
    padding: 6px 12px;
    background: var(--bg);
    border-bottom: 1px solid var(--dark-gray);
    font-size: 11px;
    color: var(--gray);
    display: flex;
    gap: 12px;
    flex-shrink: 0;
    overflow-x: auto;
  }

  .game-context::-webkit-scrollbar { height: 0; }

  .ctx-item {
    display: flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }

  .ctx-item .label { color: var(--gray); }
  .ctx-item .value { color: var(--teal); font-weight: 600; }
</style>
</head>
<body>

<!-- ═══ BUBBLE ═══ -->
<div id="bubble" onclick="toggleChat()">
  <span class="icon">⚡</span>
  <span class="badge" id="badge">0</span>
</div>

<!-- ═══ CHAT PANEL ═══ -->
<div id="chat-panel">
  <!-- Header -->
  <div class="chat-header" id="drag-handle">
    <div class="title">
      <span class="logo">⚡</span>
      <div>
        <h3>LEAGUE COACH OS</h3>
        <span class="status" id="status-text">Online</span>
      </div>
    </div>
    <div class="controls">
      <button onclick="pinChat()" title="Pin on top">📌</button>
      <button onclick="clearChat()" title="Clear history">🗑</button>
      <button onclick="toggleChat()" title="Minimize">─</button>
    </div>
  </div>

  <!-- Game Context Bar -->
  <div class="game-context" id="game-context">
    <div class="ctx-item">
      <span class="label">Champ:</span>
      <span class="value" id="ctx-champ">—</span>
    </div>
    <div class="ctx-item">
      <span class="label">vs:</span>
      <span class="value" id="ctx-opponent">—</span>
    </div>
    <div class="ctx-item">
      <span class="label">Phase:</span>
      <span class="value" id="ctx-phase">—</span>
    </div>
    <div class="ctx-item">
      <span class="label">KDA:</span>
      <span class="value" id="ctx-kda">—</span>
    </div>
  </div>

  <!-- Quick Actions -->
  <div class="quick-actions">
    <button class="quick-btn" onclick="quickAsk('What should I build next?')">
      <span class="emoji">🛒</span>Build
    </button>
    <button class="quick-btn" onclick="quickAsk('How do I beat my lane opponent?')">
      <span class="emoji">⚔️</span>Matchup
    </button>
    <button class="quick-btn" onclick="quickAsk('What should I do in teamfights?')">
      <span class="emoji">🎯</span>Teamfight
    </button>
    <button class="quick-btn" onclick="quickAsk('Am I building the right items against their comp?')">
      <span class="emoji">🔄</span>Item Check
    </button>
    <button class="quick-btn" onclick="quickAsk('What are my win conditions this game?')">
      <span class="emoji">🏆</span>Win Con
    </button>
  </div>

  <!-- Messages -->
  <div id="messages"></div>

  <!-- Typing Indicator -->
  <div class="typing-indicator" id="typing">
    <div class="dot"></div>
    <div class="dot"></div>
    <div class="dot"></div>
  </div>

  <!-- Input -->
  <div class="chat-input-area">
    <textarea id="input" placeholder="Ask your coach anything..."
              rows="1" onkeydown="handleKey(event)"
              oninput="autoResize(this)"></textarea>
    <button class="send-btn" onclick="sendMessage()">↑</button>
  </div>
</div>

<script>
  // ═══════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════
  let isOpen = false;
  let messages = [];
  let unreadCount = 0;
  const API_BASE = 'http://localhost:5050';

  // ═══════════════════════════════════════════
  // BUBBLE / CHAT TOGGLE
  // ═══════════════════════════════════════════
  function toggleChat() {
    isOpen = !isOpen;
    const panel = document.getElementById('chat-panel');
    const bubble = document.getElementById('bubble');

    if (isOpen) {
      panel.classList.add('open');
      bubble.style.display = 'none';
      unreadCount = 0;
      updateBadge();
      scrollToBottom();
      // Mark read on server
      fetch(API_BASE + '/api/mark-read', { method: 'POST' }).catch(() => {});
      // Focus input
      setTimeout(() => document.getElementById('input').focus(), 100);
    } else {
      panel.classList.remove('open');
      bubble.style.display = 'flex';
    }
  }

  function updateBadge() {
    const badge = document.getElementById('badge');
    const bubble = document.getElementById('bubble');
    if (unreadCount > 0) {
      badge.textContent = unreadCount > 9 ? '9+' : unreadCount;
      badge.classList.add('visible');
      bubble.classList.add('has-new');
    } else {
      badge.classList.remove('visible');
      bubble.classList.remove('has-new');
    }
  }

  // ═══════════════════════════════════════════
  // MESSAGES
  // ═══════════════════════════════════════════
  function renderMessage(msg) {
    const container = document.getElementById('messages');
    const div = document.createElement('div');
    div.className = `message ${msg.role} ${msg.message_type || ''}`;
    div.id = msg.id;

    let html = '';

    // Type badge for coaching messages
    if (msg.role === 'coaching' && msg.message_type && msg.message_type !== 'text') {
      html += `<span class="type-badge ${msg.message_type}">${msg.message_type}</span><br>`;
    }

    // Content (render markdown-lite: **bold**, line breaks)
    let content = msg.content || '';
    content = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    content = content.replace(/\n/g, '<br>');
    html += `<div class="content">${content}</div>`;

    // Timestamp
    if (msg.timestamp) {
      const date = new Date(msg.timestamp * 1000);
      const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      html += `<div class="timestamp">${time}</div>`;
    }

    div.innerHTML = html;
    container.appendChild(div);
    scrollToBottom();
  }

  function scrollToBottom() {
    const container = document.getElementById('messages');
    setTimeout(() => { container.scrollTop = container.scrollHeight; }, 50);
  }

  function clearChat() {
    document.getElementById('messages').innerHTML = '';
    messages = [];
    fetch(API_BASE + '/api/clear', { method: 'POST' }).catch(() => {});
  }

  function pinChat() {
    // Toggle always-on-top via pywebview
    if (window.pywebview) {
      window.pywebview.api.toggle_pin();
    }
  }

  // ═══════════════════════════════════════════
  // SENDING MESSAGES
  // ═══════════════════════════════════════════
  function sendMessage() {
    const input = document.getElementById('input');
    const text = input.value.trim();
    if (!text) return;

    // Show user message immediately
    const userMsg = {
      id: 'msg_' + Date.now(),
      role: 'user',
      content: text,
      timestamp: Date.now() / 1000
    };
    renderMessage(userMsg);
    input.value = '';
    autoResize(input);

    // Show typing indicator
    document.getElementById('typing').classList.add('visible');

    // Send to server
    fetch(API_BASE + '/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    })
    .then(r => r.json())
    .then(data => {
      document.getElementById('typing').classList.remove('visible');
      if (data.response) {
        renderMessage(data.response);
      }
    })
    .catch(err => {
      document.getElementById('typing').classList.remove('visible');
      renderMessage({
        id: 'err_' + Date.now(),
        role: 'system',
        content: 'Connection error — is the coach server running?',
        timestamp: Date.now() / 1000
      });
    });
  }

  function quickAsk(question) {
    document.getElementById('input').value = question;
    sendMessage();
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 100) + 'px';
  }

  // ═══════════════════════════════════════════
  // POLLING FOR NEW COACHING MESSAGES
  // ═══════════════════════════════════════════
  let lastMessageId = '';

  function pollMessages() {
    fetch(API_BASE + '/api/messages?after=' + lastMessageId)
      .then(r => r.json())
      .then(data => {
        if (data.messages && data.messages.length > 0) {
          data.messages.forEach(msg => {
            if (msg.id !== lastMessageId) {
              renderMessage(msg);
              lastMessageId = msg.id;
              if (!isOpen && msg.role !== 'user') {
                unreadCount++;
                updateBadge();
              }
            }
          });
        }
        // Update context bar
        if (data.context) {
          const c = data.context;
          document.getElementById('ctx-champ').textContent = c.champion || '—';
          document.getElementById('ctx-opponent').textContent = c.opponent || '—';
          document.getElementById('ctx-phase').textContent = c.phase || '—';
          document.getElementById('ctx-kda').textContent = c.kda || '—';
        }
      })
      .catch(() => {})
      .finally(() => {
        setTimeout(pollMessages, 1500);
      });
  }

  // ═══════════════════════════════════════════
  // INIT
  // ═══════════════════════════════════════════
  function init() {
    // Load existing messages
    fetch(API_BASE + '/api/messages')
      .then(r => r.json())
      .then(data => {
        if (data.messages) {
          data.messages.forEach(msg => {
            renderMessage(msg);
            lastMessageId = msg.id;
          });
        }
      })
      .catch(() => {
        renderMessage({
          id: 'init_err',
          role: 'system',
          content: 'Connecting to coach server...',
          timestamp: Date.now() / 1000
        });
      });

    // Start polling
    setTimeout(pollMessages, 2000);
  }

  init();
</script>
</body>
</html>"""


# =============================================================================
# FLASK SERVER — serves chat UI + handles API requests
# =============================================================================

def create_chat_server(chat_session: ChatSession,
                       coaching_callback: Optional[Callable] = None,
                       anthropic_client=None,
                       host: str = "127.0.0.1",
                       port: int = 5050):
    """
    Create the Flask server that powers the chat bubble.

    Endpoints:
      GET  /                → serves the chat HTML
      GET  /api/messages    → get chat history (with ?after=msg_id for polling)
      POST /api/chat        → send a user message, get AI response
      POST /api/mark-read   → mark all messages read
      POST /api/clear       → clear chat history
      POST /api/coaching    → push a coaching result (from pipeline)
    """
    try:
        from flask import Flask, request, jsonify, Response
    except ImportError:
        logger.error("Flask not installed. Run: pip install flask")
        raise

    app = Flask(__name__)

    @app.route("/")
    def index():
        return Response(CHAT_BUBBLE_HTML, mimetype="text/html")

    @app.route("/api/messages")
    def get_messages():
        after_id = request.args.get("after", "")
        msgs = chat_session.get_messages_json()

        if after_id:
            # Return only messages after the given ID
            found = False
            new_msgs = []
            for m in msgs:
                if found:
                    new_msgs.append(m)
                if m["id"] == after_id:
                    found = True
            msgs = new_msgs

        return jsonify({
            "messages": msgs,
            "context": {
                "champion": chat_session.user_champion,
                "opponent": chat_session.lane_opponent,
                "phase": chat_session.game_phase,
                "kda": "/".join(str(x) for x in chat_session.game_context.get("user", {}).get("kda", (0, 0, 0)))
                       if chat_session.game_context.get("user") else "—",
            }
        })

    @app.route("/api/chat", methods=["POST"])
    def chat():
        data = request.json or {}
        user_text = data.get("message", "").strip()
        if not user_text:
            return jsonify({"error": "empty message"}), 400

        # Add user message
        user_msg = ChatMessage(role="user", content=user_text)
        chat_session.add_message(user_msg)

        # Generate AI response
        response_msg = _generate_chat_response(user_text, chat_session, anthropic_client)
        chat_session.add_message(response_msg)

        return jsonify({"response": response_msg.to_dict()})

    @app.route("/api/mark-read", methods=["POST"])
    def mark_read():
        chat_session.mark_all_read()
        return jsonify({"ok": True})

    @app.route("/api/clear", methods=["POST"])
    def clear():
        chat_session.messages.clear()
        chat_session.unread_count = 0
        chat_session.add_message(ChatMessage(
            role="system",
            content="Chat cleared. PrintScreen for new coaching!",
            message_type="notification",
        ))
        return jsonify({"ok": True})

    @app.route("/api/coaching", methods=["POST"])
    def push_coaching():
        """Pipeline pushes coaching results here."""
        data = request.json or {}
        # Convert dict back to a coaching-style message
        msg = ChatMessage(
            role="coaching",
            content=data.get("content", ""),
            message_type=data.get("message_type", "text"),
            coaching_data=data.get("coaching_data"),
        )
        chat_session.add_message(msg)
        return jsonify({"ok": True, "message_id": msg.id})

    return app


def _generate_chat_response(user_text: str, session: ChatSession,
                             client=None) -> ChatMessage:
    """Generate an AI response to a user's freeform question."""
    if not client:
        return ChatMessage(
            role="assistant",
            content="I need an API key to answer questions. Set ANTHROPIC_API_KEY in your .env file. Meanwhile, I can still analyze your screenshots — just press PrintScreen!",
        )

    try:
        context = session.get_context_prompt()

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=context,
            messages=[{"role": "user", "content": user_text}],
        )

        return ChatMessage(
            role="assistant",
            content=response.content[0].text,
        )

    except Exception as e:
        logger.error(f"Chat response failed: {e}")
        return ChatMessage(
            role="assistant",
            content=f"Sorry, hit an error: {str(e)[:100]}. Try again or press PrintScreen for screenshot analysis!",
        )


# =============================================================================
# PYWEBVIEW LAUNCHER — creates the transparent overlay window
# =============================================================================

def launch_chat_bubble(config: Optional[Dict] = None):
    """
    Launch the chat bubble overlay.

    This creates:
    1. A Flask server on localhost:5050
    2. A pywebview transparent window loading the chat UI
    3. The window is always-on-top, frameless, and transparent

    The bubble appears as a small circle — click to expand into full chat.
    """
    config = config or {}
    api_key = config.get("anthropic_api_key", os.getenv("ANTHROPIC_API_KEY", ""))
    host = config.get("host", "127.0.0.1")
    port = config.get("port", 5050)

    # Create chat session
    session = ChatSession()

    # Anthropic client
    client = None
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            logger.info("Anthropic client initialized for chat")
        except ImportError:
            logger.warning("anthropic package not installed")

    # Create Flask app
    app = create_chat_server(session, anthropic_client=client, host=host, port=port)

    # Start Flask in background thread
    def run_server():
        app.run(host=host, port=port, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    logger.info(f"Chat server started on http://{host}:{port}")

    # Give server a moment to start
    time.sleep(0.5)

    # Try pywebview for transparent overlay
    try:
        import webview

        window = webview.create_window(
            "League Coach OS",
            url=f"http://{host}:{port}",
            width=500,
            height=700,
            x=None,   # Let OS position
            y=None,
            resizable=True,
            frameless=True,
            easy_drag=True,
            on_top=True,
            transparent=True,
            background_color='#00000000',
        )

        logger.info("Launching pywebview overlay...")
        webview.start(debug=False)

    except ImportError:
        logger.warning(
            "pywebview not installed — opening chat in browser instead. "
            "Install for overlay mode: pip install pywebview"
        )
        import webbrowser
        webbrowser.open(f"http://{host}:{port}")

        # Keep alive
        print(f"\n⚡ League Coach OS chat running at http://{host}:{port}")
        print("Press Ctrl+C to stop\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nCoach signing off. GG!")

    return session


# =============================================================================
# INTEGRATION WITH LIVE PIPELINE
# =============================================================================

class ChatBubbleIntegration:
    """
    Bridges the LiveCoachingPipeline with the chat bubble.

    When the pipeline produces coaching from a PrintScreen:
    → Posts it to the chat server → appears in chat history
    → Badge pulses on the bubble
    → Player can click to see coaching + ask follow-up questions
    """

    def __init__(self, chat_session: ChatSession, server_port: int = 5050):
        self.session = chat_session
        self.port = server_port

    def push_coaching_result(self, result):
        """Push a CoachingResult from the pipeline into the chat."""
        # Add to local session
        msg = self.session.add_coaching_result(result)

        # Also POST to server (for the UI to pick up via polling)
        try:
            import requests
            requests.post(
                f"http://127.0.0.1:{self.port}/api/coaching",
                json=msg.to_dict(),
                timeout=2.0,
            )
        except Exception:
            pass  # Server might not be running yet

        return msg

    def update_game_context(self, context: Dict):
        """Update the game context shown in the header bar."""
        self.session.game_context = context
        user = context.get("user", {})
        self.session.user_champion = user.get("champion", "")
        self.session.user_role = user.get("role", "")
        self.session.lane_opponent = user.get("lane_opponent", "")


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("⚡ Launching League Coach OS Chat Bubble...")
    launch_chat_bubble()
