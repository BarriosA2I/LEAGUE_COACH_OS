"""
================================================================================
LEAGUE COACH OS — RICH OVERLAY DISPLAY
================================================================================
Transparent always-on-top overlay that shows coaching plan during loading screen.
Renders the full GameCoachPackage in a readable, game-friendly format.

Features:
- Always-on-top transparent window
- Cyberpunk teal/gold theme matching Barrios A2I brand
- Auto-dismiss after configurable duration
- Keyboard shortcut to toggle (F9)
- Compact view vs expanded view toggle
- Click-through mode (doesn't capture mouse)

Author: Barrios A2I | Version: 1.0.0
================================================================================
"""
from __future__ import annotations  # Deferred annotation evaluation — prevents tk.Frame errors

import json
import sys
import threading
import time
from typing import Any, Dict, Optional

try:
    import tkinter as tk
    from tkinter import font as tkfont
    HAS_TK = True
except (ImportError, ModuleNotFoundError):
    tk = None
    tkfont = None
    HAS_TK = False

try:
    import keyboard  # for global hotkey
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False


# =============================================================================
# COLOR THEME — Barrios A2I Cyberpunk
# =============================================================================

class Theme:
    BG = "#0a0e17"               # Deep space black
    BG_ALPHA = 0.92              # Overlay transparency
    PANEL_BG = "#111827"         # Panel background
    BORDER = "#00CED1"           # Crystalline teal
    ACCENT = "#00CED1"           # Primary accent
    GOLD = "#FFD700"             # Gold highlights
    TEXT = "#E5E7EB"             # Light gray text
    TEXT_DIM = "#9CA3AF"         # Dimmed text
    TEXT_BRIGHT = "#FFFFFF"      # Bright white
    SUCCESS = "#10B981"          # Green
    DANGER = "#EF4444"           # Red
    WARNING = "#F59E0B"          # Amber
    BLUE_TEAM = "#3B82F6"        # Blue team color
    RED_TEAM = "#EF4444"         # Red team color

    # Font sizes
    TITLE_SIZE = 16
    HEADER_SIZE = 13
    BODY_SIZE = 11
    SMALL_SIZE = 9


# =============================================================================
# OVERLAY WINDOW
# =============================================================================

class CoachOverlay:
    """
    Transparent overlay window showing the coaching plan.

    Renders on top of the game with:
    - User champion + role + matchup header
    - Build path (items + runes)
    - Lane plan summary
    - Team fight plan
    - Next 30 seconds quick tips
    """

    def __init__(self, duration: int = 30, position: str = "top-right", width: int = 460):
        self.duration = duration
        self.position = position
        self.width = width
        self.root: Optional[tk.Tk] = None
        self._visible = False
        self._expanded = False
        self._thread: Optional[threading.Thread] = None

    def show(self, coaching_data: Dict[str, Any]):
        """Show the overlay with coaching data. Runs in its own thread."""
        if self._thread and self._thread.is_alive():
            # Update existing overlay
            self._update_data(coaching_data)
            return

        self._thread = threading.Thread(
            target=self._create_window,
            args=(coaching_data,),
            daemon=True,
            name="coach-overlay"
        )
        self._thread.start()

    def _create_window(self, data: Dict):
        """Create the Tkinter overlay window."""
        if not HAS_TK:
            return

        self.root = tk.Tk()
        self.root.title("League Coach OS")
        self.root.overrideredirect(True)       # No title bar
        self.root.attributes("-topmost", True)  # Always on top
        self.root.configure(bg=Theme.BG)

        # Transparency (Windows)
        if sys.platform == "win32":
            self.root.attributes("-alpha", Theme.BG_ALPHA)
            # Make a specific color transparent for click-through
            self.root.wm_attributes("-transparentcolor", "")

        # Position window
        self._position_window()

        # Build the UI
        self._build_ui(data)

        # Register global hotkey
        if HAS_KEYBOARD:
            keyboard.add_hotkey("F9", self._toggle_visibility)

        # Auto-dismiss timer
        self.root.after(self.duration * 1000, self._dismiss)

        # Allow dragging
        self.root.bind("<Button-1>", self._start_drag)
        self.root.bind("<B1-Motion>", self._do_drag)

        # ESC to dismiss
        self.root.bind("<Escape>", lambda e: self._dismiss())

        self._visible = True
        self.root.mainloop()

    def _position_window(self):
        """Position the overlay on screen."""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        height = 600  # Will auto-adjust

        positions = {
            "top-right": (screen_w - self.width - 20, 40),
            "top-left": (20, 40),
            "center": ((screen_w - self.width) // 2, (screen_h - height) // 2),
            "bottom-right": (screen_w - self.width - 20, screen_h - height - 60),
        }
        x, y = positions.get(self.position, positions["top-right"])
        self.root.geometry(f"{self.width}x{height}+{x}+{y}")

    def _build_ui(self, data: Dict):
        """Build the coaching overlay UI."""
        # Main container with border
        main = tk.Frame(self.root, bg=Theme.BG, highlightbackground=Theme.BORDER,
                        highlightthickness=2, padx=12, pady=8)
        main.pack(fill=tk.BOTH, expand=True)

        # === HEADER ===
        self._build_header(main, data)

        # === SEPARATOR ===
        tk.Frame(main, bg=Theme.BORDER, height=1).pack(fill=tk.X, pady=6)

        # === SCROLLABLE CONTENT ===
        canvas = tk.Canvas(main, bg=Theme.BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(main, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg=Theme.BG)

        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel scroll
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # === BUILD SECTION ===
        self._build_section(content, "🔨 BUILD", self._format_build(data.get("build", {})))

        # === LANE PLAN ===
        self._build_section(content, "⚔️  LANE PLAN", self._format_lane_plan(data.get("lane_plan", {})))

        # === BEAT ENEMY ===
        self._build_section(content, "🎯 BEAT ENEMY", self._format_beat_enemy(data.get("beat_enemy", {})))

        # === TEAM PLAN ===
        self._build_section(content, "👥 TEAM PLAN", self._format_team_plan(data.get("team_plan", {})))

        # === NEXT 30 SECONDS ===
        self._build_next30(content, data.get("next_30_seconds", {}))

        # === FOOTER ===
        self._build_footer(main, data)

    def _build_header(self, parent: tk.Frame, data: Dict):
        """Build the header with champion, role, and matchup info."""
        header = tk.Frame(parent, bg=Theme.BG)
        header.pack(fill=tk.X)

        user = data.get("user", {})
        champ = user.get("champion", "Unknown")
        role = user.get("role", "?")
        opponent = user.get("lane_opponent", "Unknown")

        # Title row
        title_frame = tk.Frame(header, bg=Theme.BG)
        title_frame.pack(fill=tk.X)

        tk.Label(
            title_frame, text="LEAGUE COACH OS",
            bg=Theme.BG, fg=Theme.ACCENT,
            font=("Consolas", Theme.SMALL_SIZE, "bold")
        ).pack(side=tk.LEFT)

        tk.Label(
            title_frame, text="×",
            bg=Theme.BG, fg=Theme.TEXT_DIM,
            font=("Consolas", Theme.TITLE_SIZE), cursor="hand2"
        ).pack(side=tk.RIGHT)

        # Champion info
        champ_frame = tk.Frame(header, bg=Theme.BG)
        champ_frame.pack(fill=tk.X, pady=(4, 0))

        tk.Label(
            champ_frame, text=f"🎮 {champ}",
            bg=Theme.BG, fg=Theme.GOLD,
            font=("Segoe UI", Theme.TITLE_SIZE, "bold")
        ).pack(side=tk.LEFT)

        tk.Label(
            champ_frame, text=f"  {role}  ",
            bg=Theme.ACCENT, fg=Theme.BG,
            font=("Consolas", Theme.SMALL_SIZE, "bold"),
            padx=6, pady=1
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Matchup
        if opponent and opponent != "Unknown":
            tk.Label(
                champ_frame, text=f"vs {opponent}",
                bg=Theme.BG, fg=Theme.DANGER,
                font=("Segoe UI", Theme.HEADER_SIZE)
            ).pack(side=tk.LEFT, padx=(12, 0))

        # Teams row
        teams = data.get("teams", {})
        blue = teams.get("blue", [])
        red = teams.get("red", [])
        if blue or red:
            teams_frame = tk.Frame(header, bg=Theme.BG)
            teams_frame.pack(fill=tk.X, pady=(4, 0))

            if blue:
                tk.Label(
                    teams_frame, text=f"🔵 {' · '.join(blue[:5])}",
                    bg=Theme.BG, fg=Theme.BLUE_TEAM,
                    font=("Consolas", Theme.SMALL_SIZE)
                ).pack(anchor=tk.W)
            if red:
                tk.Label(
                    teams_frame, text=f"🔴 {' · '.join(red[:5])}",
                    bg=Theme.BG, fg=Theme.RED_TEAM,
                    font=("Consolas", Theme.SMALL_SIZE)
                ).pack(anchor=tk.W)

    def _build_section(self, parent: tk.Frame, title: str, lines: list):
        """Build a collapsible section."""
        section = tk.Frame(parent, bg=Theme.PANEL_BG, padx=8, pady=6,
                          highlightbackground=Theme.BORDER, highlightthickness=1)
        section.pack(fill=tk.X, pady=4)

        # Section title
        tk.Label(
            section, text=title,
            bg=Theme.PANEL_BG, fg=Theme.ACCENT,
            font=("Segoe UI", Theme.HEADER_SIZE, "bold"),
            anchor=tk.W
        ).pack(fill=tk.X)

        # Content lines
        for line in lines:
            color = Theme.TEXT
            if line.startswith("✅") or line.startswith("→"):
                color = Theme.SUCCESS
            elif line.startswith("🚫") or line.startswith("⚠"):
                color = Theme.DANGER
            elif line.startswith("💡"):
                color = Theme.GOLD

            tk.Label(
                section, text=line,
                bg=Theme.PANEL_BG, fg=color,
                font=("Segoe UI", Theme.BODY_SIZE),
                anchor=tk.W, wraplength=self.width - 60, justify=tk.LEFT
            ).pack(fill=tk.X, pady=1)

    def _build_next30(self, parent: tk.Frame, n30: Dict):
        """Build the highlighted NEXT 30 SECONDS section."""
        section = tk.Frame(parent, bg="#0d2818", padx=8, pady=6,
                          highlightbackground=Theme.SUCCESS, highlightthickness=2)
        section.pack(fill=tk.X, pady=6)

        tk.Label(
            section, text="⚡ NEXT 30 SECONDS",
            bg="#0d2818", fg=Theme.GOLD,
            font=("Segoe UI", Theme.HEADER_SIZE, "bold")
        ).pack(anchor=tk.W)

        dos = n30.get("do", [])
        avoids = n30.get("avoid", [])

        for tip in dos[:3]:
            tk.Label(
                section, text=f"  ✅ {tip}",
                bg="#0d2818", fg=Theme.SUCCESS,
                font=("Segoe UI", Theme.BODY_SIZE),
                anchor=tk.W, wraplength=self.width - 60, justify=tk.LEFT
            ).pack(fill=tk.X, pady=1)

        for tip in avoids[:3]:
            tk.Label(
                section, text=f"  🚫 {tip}",
                bg="#0d2818", fg=Theme.DANGER,
                font=("Segoe UI", Theme.BODY_SIZE),
                anchor=tk.W, wraplength=self.width - 60, justify=tk.LEFT
            ).pack(fill=tk.X, pady=1)

    def _build_footer(self, parent: tk.Frame, data: Dict):
        """Build footer with meta info."""
        footer = tk.Frame(parent, bg=Theme.BG)
        footer.pack(fill=tk.X, pady=(4, 0))

        meta = data.get("meta", {})
        latency = meta.get("total_latency_ms", 0)
        cost = meta.get("total_cost_usd", 0)
        mode = meta.get("mode", "FAST")

        tk.Label(
            footer,
            text=f"⚡ {latency:.0f}ms  |  💰 ${cost:.4f}  |  {mode} MODE  |  F9=toggle  ESC=close",
            bg=Theme.BG, fg=Theme.TEXT_DIM,
            font=("Consolas", Theme.SMALL_SIZE)
        ).pack(side=tk.LEFT)

    # === FORMATTERS ===

    def _format_build(self, build: Dict) -> list:
        lines = []
        runes = build.get("runes", {})
        if runes:
            keystone = runes.get("primary", ["?"])[0] if isinstance(runes.get("primary"), list) else "?"
            lines.append(f"📜 Keystone: {keystone}")
            tree = runes.get("primary_tree", "?")
            secondary = runes.get("secondary_tree", "?")
            lines.append(f"   {tree} / {secondary}")

        summoners = build.get("summoners", [])
        if summoners:
            lines.append(f"🔮 Summs: {' + '.join(summoners)}")

        start = build.get("start_items", [])
        if start:
            lines.append(f"🏁 Start: {', '.join(start)}")

        core = build.get("core_items", [])
        if core:
            lines.append(f"⚔️  Core: {' → '.join(core[:4])}")

        boots = build.get("boots", "")
        if boots:
            lines.append(f"👟 Boots: {boots}")

        situational = build.get("situational_items", [])
        if situational:
            lines.append(f"🔧 Flex: {', '.join(situational[:3])}")

        skill = build.get("skill_order", {})
        max_order = skill.get("max_order", [])
        if max_order:
            lines.append(f"📊 Max: {' > '.join(max_order)}")

        return lines or ["No build data available"]

    def _format_lane_plan(self, lane: Dict) -> list:
        lines = []
        l13 = lane.get("levels_1_3", "")
        if l13:
            lines.append(f"Lvl 1-3: {l13}")

        wave = lane.get("wave_plan", "")
        if wave:
            lines.append(f"💡 Wave: {wave}")

        trades = lane.get("trade_windows", "")
        if trades:
            lines.append(f"⚔️  Trades: {trades}")

        recall = lane.get("first_recall", {})
        if recall:
            gold = recall.get("goal_gold", "?")
            buy = recall.get("buy", "?")
            lines.append(f"🏠 Recall @ {gold}g → {buy}")

        l6 = lane.get("level_6", "")
        if l6:
            lines.append(f"⭐ Lvl 6: {l6}")

        return lines or ["No lane plan available"]

    def _format_beat_enemy(self, beat: Dict) -> list:
        lines = []
        threats = beat.get("biggest_threats", [])
        for t in threats[:3]:
            lines.append(f"⚠️  {t}")

        punish = beat.get("how_to_punish", [])
        for p in punish[:3]:
            lines.append(f"✅ {p}")

        dont = beat.get("what_not_to_do", [])
        for d in dont[:3]:
            lines.append(f"🚫 {d}")

        return lines or ["No enemy analysis available"]

    def _format_team_plan(self, team: Dict) -> list:
        lines = []
        wc = team.get("win_condition", "")
        if wc:
            lines.append(f"🏆 Win con: {wc}")

        job = team.get("your_job", "")
        if job:
            lines.append(f"📋 Your job: {job}")

        target = team.get("target_priority", "")
        if target:
            lines.append(f"🎯 Focus: {target}")

        rules = team.get("fight_rules", "")
        if rules:
            lines.append(f"📖 Rules: {rules}")

        return lines or ["No team plan available"]

    # === WINDOW CONTROLS ===

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event):
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _toggle_visibility(self):
        if self._visible:
            self.root.withdraw()
            self._visible = False
        else:
            self.root.deiconify()
            self._visible = True

    def _dismiss(self):
        if self.root:
            self.root.destroy()
            self._visible = False

    def _update_data(self, data: Dict):
        """Update overlay with new data (for mid-game updates)."""
        # For now, destroy and recreate. Future: hot-swap content.
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
        self._create_window(data)


# =============================================================================
# CONSOLE OVERLAY (Fallback when no GUI available)
# =============================================================================

class ConsoleOverlay:
    """Fallback text-based overlay for headless/SSH environments."""

    BORDER = "═"
    ACCENT = "\033[96m"   # Cyan
    GOLD = "\033[93m"     # Yellow
    GREEN = "\033[92m"    # Green
    RED = "\033[91m"      # Red
    DIM = "\033[90m"      # Gray
    BOLD = "\033[1m"
    RESET = "\033[0m"

    def show(self, data: Dict[str, Any]):
        user = data.get("user", {})
        build = data.get("build", {})
        lane = data.get("lane_plan", {})
        beat = data.get("beat_enemy", {})
        team = data.get("team_plan", {})
        n30 = data.get("next_30_seconds", {})
        meta = data.get("meta", {})
        teams = data.get("teams", {})

        c = self  # shorthand for colors

        print(f"\n{c.ACCENT}{'═'*60}{c.RESET}")
        print(f"{c.ACCENT}  ⚡ LEAGUE COACH OS — Barrios A2I{c.RESET}")
        print(f"{c.ACCENT}{'═'*60}{c.RESET}")

        # User info
        champ = user.get("champion", "?")
        role = user.get("role", "?")
        opponent = user.get("lane_opponent", "?")
        print(f"\n  {c.GOLD}{c.BOLD}🎮 {champ} ({role}){c.RESET} vs {c.RED}{opponent}{c.RESET}")

        # Teams
        blue = teams.get("blue", [])
        red = teams.get("red", [])
        if blue:
            print(f"  {c.ACCENT}🔵 {' · '.join(blue)}{c.RESET}")
        if red:
            print(f"  {c.RED}🔴 {' · '.join(red)}{c.RESET}")

        # Build
        print(f"\n  {c.ACCENT}{c.BOLD}🔨 BUILD{c.RESET}")
        core = build.get("core_items", [])
        if core:
            print(f"  Core: {' → '.join(core[:4])}")
        runes = build.get("runes", {})
        if runes:
            primary = runes.get("primary", [])
            keystone = primary[0] if primary else "?"
            print(f"  Keystone: {keystone}")
        skill = build.get("skill_order", {})
        max_order = skill.get("max_order", [])
        if max_order:
            print(f"  Max: {' > '.join(max_order)}")

        # Lane plan
        print(f"\n  {c.ACCENT}{c.BOLD}⚔️  LANE PLAN{c.RESET}")
        l13 = lane.get("levels_1_3", "")
        if l13:
            print(f"  Lvl 1-3: {l13}")
        recall = lane.get("first_recall", {})
        if recall:
            print(f"  Recall @ {recall.get('goal_gold', '?')}g → {recall.get('buy', '?')}")

        # Next 30 seconds
        print(f"\n  {c.GREEN}{c.BOLD}⚡ NEXT 30 SECONDS{c.RESET}")
        for tip in n30.get("do", [])[:3]:
            print(f"  {c.GREEN}  ✅ {tip}{c.RESET}")
        for tip in n30.get("avoid", [])[:3]:
            print(f"  {c.RED}  🚫 {tip}{c.RESET}")

        # Footer
        latency = meta.get("total_latency_ms", 0)
        cost = meta.get("total_cost_usd", 0)
        print(f"\n{c.DIM}  ⚡ {latency:.0f}ms | 💰 ${cost:.4f} | {meta.get('mode', 'FAST')}{c.RESET}")
        print(f"{c.ACCENT}{'═'*60}{c.RESET}\n")


# =============================================================================
# OVERLAY FACTORY
# =============================================================================

def create_overlay(prefer_gui: bool = True) -> Any:
    """Create the best available overlay for this system."""
    if prefer_gui and HAS_TK:
        return CoachOverlay()
    else:
        return ConsoleOverlay()


if __name__ == "__main__":
    # Demo with sample data
    sample = {
        "user": {"champion": "Darius", "role": "Top", "lane_opponent": "Garen"},
        "teams": {
            "blue": ["Darius", "Lee Sin", "Ahri", "Jinx", "Thresh"],
            "red": ["Garen", "Vi", "Syndra", "Caitlyn", "Leona"]
        },
        "build": {
            "summoners": ["Flash", "Teleport"],
            "runes": {"primary_tree": "Precision", "primary": ["Conqueror", "Triumph", "Legend: Tenacity", "Last Stand"],
                      "secondary_tree": "Resolve", "secondary": ["Bone Plating", "Unflinching"]},
            "skill_order": {"max_order": ["Q", "E", "W"]},
            "start_items": ["Doran's Blade", "Health Potion"],
            "core_items": ["Trinity Force", "Sterak's Gage", "Dead Man's Plate"],
            "boots": "Plated Steelcaps",
            "situational_items": ["Spirit Visage", "Randuin's Omen", "Guardian Angel"],
        },
        "lane_plan": {
            "levels_1_3": "Look for short trades with auto-W-auto. Darius passive stacks win extended fights.",
            "wave_plan": "Freeze near your tower. Garen has no gap close pre-6.",
            "trade_windows": "Trade when Garen Q is on cooldown (8s). Pull him with E after he Qs.",
            "first_recall": {"goal_gold": 1050, "timing_rule": "After killing or forcing recall", "buy": "Phage + Boots"},
            "level_6": "All-in at 5 stacks of passive. R executes below 25% HP.",
        },
        "beat_enemy": {
            "biggest_threats": ["Garen silence (Q) stops your combo", "Garen W gives 60% tenacity", "Garen R is true damage execute"],
            "how_to_punish": ["Auto-W when he walks up to CS", "E pull after he wastes Q on minion", "Stack passive to 5 before ulting"],
            "what_not_to_do": ["Don't fight inside his E spin", "Don't ult without 5 stacks", "Don't push without vision"],
        },
        "team_plan": {
            "win_condition": "Win lane hard, TP bot for dragon fights, become teamfight frontline",
            "your_job": "Frontline engage, pull carries with E, stack passive in fights, dunk resets",
            "target_priority": "Caitlyn > Syndra > Vi > Leona > Garen",
            "fight_rules": "Flash-E onto Caitlyn. Don't waste ult without 5-stack Noxian Might.",
        },
        "next_30_seconds": {
            "do": ["Take Doran's Blade + pot start", "Walk to lane through tri-brush", "Auto-W Garen if he contests first 3 melee minions"],
            "avoid": ["Don't waste mana on Q poke level 1", "Don't push wave — let it slow push to you", "Don't fight in Garen E spin range"],
        },
        "meta": {"total_latency_ms": 4200, "total_cost_usd": 0.018, "mode": "FAST", "patch_version": "25.S1.3"},
    }

    overlay = create_overlay(prefer_gui="--gui" in sys.argv)
    overlay.show(sample)
