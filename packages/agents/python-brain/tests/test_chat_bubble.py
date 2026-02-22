"""
================================================================================
LEAGUE COACH OS — CHAT BUBBLE TESTS
================================================================================
Tests the chat bubble overlay system:
  • ChatSession message management
  • Coaching result → chat message conversion
  • Game context tracking across messages
  • Quick action questions
  • Message polling (after ID filtering)
  • Flask server endpoints

Run: python tests/test_chat_bubble.py
================================================================================
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_chat_session_basics():
    """Test ChatSession message management."""
    from daemon.chat_bubble import ChatSession, ChatMessage

    session = ChatSession()

    # Should have welcome message
    assert len(session.messages) == 1, f"Expected 1 welcome msg, got {len(session.messages)}"
    assert session.messages[0].role == "system"
    print("  ✅ Welcome message present")

    # Add messages
    session.add_message(ChatMessage(role="user", content="How do I beat Darius?"))
    session.add_message(ChatMessage(role="assistant", content="Poke him at range, avoid his E pull"))
    assert len(session.messages) == 3
    print("  ✅ Messages added correctly")

    # Unread tracking
    assert session.unread_count == 1  # Only assistant counts as unread
    session.mark_all_read()
    assert session.unread_count == 0
    print("  ✅ Unread count tracking works")

    # JSON serialization
    msgs_json = session.get_messages_json()
    assert len(msgs_json) == 3
    assert all("id" in m and "role" in m and "content" in m for m in msgs_json)
    print("  ✅ JSON serialization works")

    # Max history enforcement
    for i in range(250):
        session.add_message(ChatMessage(role="user", content=f"Message {i}"))
    assert len(session.messages) <= session.max_history + 10  # Some slack for pinned
    print("  ✅ Max history enforced")

    return 5, 5


def test_coaching_result_to_chat():
    """Test converting CoachingResult into chat messages."""
    from daemon.chat_bubble import ChatSession
    from daemon.live_pipeline import CoachingResult

    session = ChatSession()
    session.user_champion = "Jinx"
    session.user_role = "ADC"

    # Build advice coaching result
    build_result = CoachingResult(
        game_state="tab_scoreboard",
        game_phase="early",
        headline="Rush Infinity Edge — enemy has no armor",
        next_30_seconds=["Buy BF Sword (1300g)", "Get boots", "Ward river"],
        buy_now=[{"item": "BF Sword", "gold": 1300, "reason": "Core AD component", "priority": 1}],
        full_build=["Infinity Edge", "Rapid Firecannon", "Lord Dominik's"],
    )

    msg = session.add_coaching_result(build_result)
    assert msg.role == "coaching"
    assert msg.message_type == "build"
    assert "Infinity Edge" in msg.content
    assert "BF Sword" in msg.content
    print("  ✅ Build coaching → chat message")

    # Bot lane matchup
    bot_result = CoachingResult(
        game_state="in_game_laning",
        game_phase="early",
        headline="vs Caitlyn/Thresh: dodge hook, punish when E is down",
        is_botlane=True,
        enemy_adc="Caitlyn",
        enemy_support="Thresh",
        their_kill_combo="Thresh hook → Cait trap → headshot",
        your_win_condition="All-in after Thresh misses hook (20s CD lvl 1)",
    )

    msg2 = session.add_coaching_result(bot_result)
    assert msg2.message_type == "matchup"
    assert "Caitlyn" in msg2.content
    assert "Thresh" in msg2.content
    assert "hook" in msg2.content.lower()
    print("  ✅ Bot lane coaching → chat message")

    # Death review
    death_result = CoachingResult(
        game_state="death_screen",
        headline="Death #1: caught by Thresh hook in river",
        death_reason="Walked into river without vision",
        death_fix="Ward river before rotating",
        death_count=1,
    )

    msg3 = session.add_coaching_result(death_result)
    assert msg3.message_type == "death"
    assert "Death #1" in msg3.content
    print("  ✅ Death coaching → chat message")

    # Context updates from coaching
    assert session.lane_opponent == ""  # Bot lane doesn't set single laner
    assert session.game_phase == "early" or session.game_phase == ""  # Phase updated when available
    assert len(session.current_build) > 0  # Build updated from first result
    print("  ✅ Game context updated from coaching")

    return 4, 4


def test_game_context_prompt():
    """Test that the AI context prompt includes game state."""
    from daemon.chat_bubble import ChatSession, ChatMessage

    session = ChatSession()
    session.user_champion = "Darius"
    session.user_role = "Top"
    session.lane_opponent = "Garen"
    session.game_phase = "mid_laning"
    session.current_build = ["Trinity Force", "Sterak's Gage"]
    session.game_context = {
        "user": {
            "champion": "Darius",
            "kda": (3, 1, 2),
            "cs": 120,
        }
    }

    # Add some conversation
    session.add_message(ChatMessage(role="user", content="Should I build armor pen?"))
    session.add_message(ChatMessage(role="assistant", content="Yes, Garen is stacking armor"))

    prompt = session.get_context_prompt()

    checks = [
        ("contains champion", "Darius" in prompt),
        ("contains role", "Top" in prompt),
        ("contains opponent", "Garen" in prompt),
        ("contains phase", "mid_laning" in prompt),
        ("contains build", "Trinity Force" in prompt),
        ("contains conversation", "armor pen" in prompt),
        ("has coach persona", "expert" in prompt.lower() or "coach" in prompt.lower()),
    ]

    passed = 0
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        if ok:
            passed += 1

    return passed, len(checks)


def test_message_polling_filter():
    """Test that message polling correctly filters by after_id."""
    from daemon.chat_bubble import ChatSession, ChatMessage

    session = ChatSession(max_history=200)

    # Clear welcome message for clean test
    session.messages.clear()

    # Add several messages
    msg1 = session.add_message(ChatMessage(role="user", content="msg 1"))
    msg2 = session.add_message(ChatMessage(role="assistant", content="msg 2"))
    msg3 = session.add_message(ChatMessage(role="user", content="msg 3"))
    msg4 = session.add_message(ChatMessage(role="assistant", content="msg 4"))

    all_msgs = session.get_messages_json()
    # Filter: get messages after msg2
    after_id = msg2.id
    found = False
    new_msgs = []
    for m in all_msgs:
        if found:
            new_msgs.append(m)
        if m["id"] == after_id:
            found = True

    assert len(new_msgs) == 2  # msg3 and msg4
    assert new_msgs[0]["content"] == "msg 3"
    assert new_msgs[1]["content"] == "msg 4"
    print("  ✅ After-ID filtering returns correct messages")

    # Filter with last ID — should return empty
    after_id = msg4.id
    found = False
    new_msgs = []
    for m in all_msgs:
        if found:
            new_msgs.append(m)
        if m["id"] == after_id:
            found = True
    assert len(new_msgs) == 0
    print("  ✅ No new messages when at latest")

    return 2, 2


def test_pinned_messages_survive_trim():
    """Test that pinned messages survive history trimming."""
    from daemon.chat_bubble import ChatSession, ChatMessage

    session = ChatSession(max_history=20)

    # Pin a coaching message
    pinned = session.add_message(ChatMessage(
        role="coaching",
        content="IMPORTANT: Build path — Trinity Force → Sterak's → Dead Man's",
        is_pinned=True,
    ))

    # Flood with messages to trigger trim
    for i in range(50):
        session.add_message(ChatMessage(role="user", content=f"Filler {i}"))

    # Pinned message should survive
    pinned_ids = [m.id for m in session.messages if m.is_pinned]
    assert pinned.id in pinned_ids, "Pinned message was trimmed!"
    print("  ✅ Pinned messages survive history trim")

    return 1, 1


def test_flask_server_creation():
    """Test that the Flask server creates correctly with all endpoints."""
    from daemon.chat_bubble import ChatSession, create_chat_server

    session = ChatSession()

    try:
        app = create_chat_server(session)

        # Check that all routes exist
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        expected_routes = ["/", "/api/messages", "/api/chat", "/api/mark-read",
                          "/api/clear", "/api/coaching"]

        passed = 0
        for route in expected_routes:
            has_route = route in rules
            print(f"  {'✅' if has_route else '❌'} Route: {route}")
            if has_route:
                passed += 1

        return passed, len(expected_routes)

    except ImportError:
        print("  ⚠️ Flask not installed — skipping server tests")
        return 0, 0


def test_flask_endpoints():
    """Test the actual Flask endpoint responses."""
    from daemon.chat_bubble import ChatSession, ChatMessage, create_chat_server

    session = ChatSession()

    try:
        app = create_chat_server(session)
        client = app.test_client()

        # GET / → should return HTML
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"LEAGUE COACH OS" in resp.data
        print("  ✅ GET / returns chat HTML")

        # GET /api/messages → should return message list
        resp = client.get("/api/messages")
        data = json.loads(resp.data)
        assert "messages" in data
        assert "context" in data
        assert len(data["messages"]) >= 1  # Welcome message
        print("  ✅ GET /api/messages returns history")

        # POST /api/mark-read
        resp = client.post("/api/mark-read")
        assert resp.status_code == 200
        print("  ✅ POST /api/mark-read works")

        # POST /api/coaching → push a coaching message
        resp = client.post("/api/coaching", json={
            "content": "Buy Infinity Edge next",
            "message_type": "build",
        })
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"]
        print("  ✅ POST /api/coaching pushes message")

        # Verify coaching message appears in history
        resp = client.get("/api/messages")
        data = json.loads(resp.data)
        has_coaching = any(m["content"] == "Buy Infinity Edge next" for m in data["messages"])
        assert has_coaching
        print("  ✅ Coaching message appears in history")

        # POST /api/clear
        resp = client.post("/api/clear")
        assert resp.status_code == 200
        resp = client.get("/api/messages")
        data = json.loads(resp.data)
        assert len(data["messages"]) == 1  # Only the "cleared" system message
        print("  ✅ POST /api/clear resets history")

        return 6, 6

    except ImportError:
        print("  ⚠️ Flask not installed — skipping endpoint tests")
        return 0, 0


def test_chat_html_content():
    """Test that the HTML template has all required UI elements."""
    from daemon.chat_bubble import CHAT_BUBBLE_HTML

    checks = [
        ("has bubble div", 'id="bubble"' in CHAT_BUBBLE_HTML),
        ("has chat panel", 'id="chat-panel"' in CHAT_BUBBLE_HTML),
        ("has messages area", 'id="messages"' in CHAT_BUBBLE_HTML),
        ("has input textarea", 'id="input"' in CHAT_BUBBLE_HTML),
        ("has send button", "send-btn" in CHAT_BUBBLE_HTML),
        ("has quick action buttons", "quick-btn" in CHAT_BUBBLE_HTML),
        ("has game context bar", "game-context" in CHAT_BUBBLE_HTML),
        ("has typing indicator", "typing-indicator" in CHAT_BUBBLE_HTML),
        ("has teal theme color", "#00CED1" in CHAT_BUBBLE_HTML or "var(--teal)" in CHAT_BUBBLE_HTML),
        ("has toggle function", "toggleChat" in CHAT_BUBBLE_HTML),
        ("has polling function", "pollMessages" in CHAT_BUBBLE_HTML),
        ("has badge for unread", "badge" in CHAT_BUBBLE_HTML),
        ("has Build quick action", "Build" in CHAT_BUBBLE_HTML),
        ("has Matchup quick action", "Matchup" in CHAT_BUBBLE_HTML),
        ("has Teamfight quick action", "Teamfight" in CHAT_BUBBLE_HTML),
    ]

    passed = 0
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        if ok:
            passed += 1

    return passed, len(checks)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("  LEAGUE COACH OS — CHAT BUBBLE TESTS")
    print("=" * 60)

    total_passed = 0
    total_tests = 0

    tests = [
        ("Chat Session Basics", test_chat_session_basics),
        ("Coaching Result → Chat Message", test_coaching_result_to_chat),
        ("Game Context Prompt", test_game_context_prompt),
        ("Message Polling Filter", test_message_polling_filter),
        ("Pinned Messages Survive Trim", test_pinned_messages_survive_trim),
        ("Flask Server Creation", test_flask_server_creation),
        ("Flask Endpoint Responses", test_flask_endpoints),
        ("Chat HTML Content", test_chat_html_content),
    ]

    for name, test_fn in tests:
        print(f"\n{'─' * 50}")
        print(f"  TEST: {name}")
        print(f"{'─' * 50}")
        try:
            passed, total = test_fn()
            total_passed += passed
            total_tests += total
            status = "✅" if passed == total else "⚠️"
            print(f"\n  {status} {passed}/{total} passed")
        except Exception as e:
            print(f"\n  ❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            total_tests += 1

    print(f"\n{'=' * 60}")
    print(f"  TOTAL: {total_passed}/{total_tests} passed")
    all_pass = total_passed == total_tests
    print(f"  {'✅ ALL TESTS PASSED' if all_pass else '⚠️ SOME TESTS FAILED'}")
    print(f"{'=' * 60}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
