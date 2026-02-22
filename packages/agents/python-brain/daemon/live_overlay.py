"""
================================================================================
LEAGUE COACH OS — LIVE OVERLAY v2.0
================================================================================
Renders coaching advice as a transparent always-on-top overlay.

Supports ALL game states:
  • Loading screen → Full pre-game plan
  • TAB/Shop → Build advice with buy order
  • In-lane → Matchup tips, trade patterns, cooldowns
  • Bot lane → Dual-threat: both enemy ADC + Support
  • Death → Quick review + recovery plan
  • Teamfight → Target priority, positioning, combo

Cyberpunk teal/gold theme. Auto-dismiss. Draggable. F9 toggle.

Author: Barrios A2I | Version: 2.0.0
================================================================================
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("league_coach.overlay")


# =============================================================================
# THEME COLORS
# =============================================================================

class Theme:
    BG = "#0D1117"
    BG_SECTION = "#161B22"
    BG_HIGHLIGHT = "#1C2333"
    TEAL = "#00CED1"
    GOLD = "#FFD700"
    GREEN = "#10B981"
    RED = "#EF4444"
    ORANGE = "#F59E0B"
    BLUE = "#3B82F6"
    PURPLE = "#A855F7"
    WHITE = "#E6EDF3"
    GRAY = "#8B949E"
    DARK_GRAY = "#30363D"
    FONT = "Segoe UI"
    FONT_MONO = "Consolas"


# =============================================================================
# CONSOLE OVERLAY (works everywhere — SSH, headless, no tkinter)
# =============================================================================

class ConsoleOverlay:
    """Renders coaching to terminal with ANSI colors."""

    # ANSI color codes
    TEAL = "\033[96m"
    GOLD = "\033[93m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    DIM = "\033[2m"

    def show(self, result: Any):
        """Render a CoachingResult to the console."""
        T = self.TEAL
        G = self.GOLD
        GR = self.GREEN
        R = self.RED
        W = self.WHITE
        GY = self.GRAY
        B = self.BOLD
        RS = self.RESET
        D = self.DIM

        state = getattr(result, 'game_state', 'unknown')
        phase = getattr(result, 'game_phase', '')

        # Header
        print(f"\n{T}{'═' * 60}{RS}")
        print(f"{T}  ⚡ LEAGUE COACH OS — LIVE{RS}")
        print(f"{GY}  State: {state} | Phase: {phase} | {result.processing_time:.1f}s{RS}")
        print(f"{T}{'═' * 60}{RS}")

        # Headline
        headline = getattr(result, 'headline', '')
        if headline:
            print(f"\n  {B}{G}{headline}{RS}")

        # Next 30 seconds
        tips = getattr(result, 'next_30_seconds', [])
        if tips:
            print(f"\n  {T}▸ NEXT 30 SECONDS{RS}")
            for i, tip in enumerate(tips[:3], 1):
                color = GR if i == 1 else W
                print(f"    {color}{i}. {tip}{RS}")

        # Build advice
        buy_now = getattr(result, 'buy_now', [])
        if buy_now:
            print(f"\n  {G}🛒 BUY NOW{RS}")
            for item in buy_now:
                name = item.get('item', '?')
                gold = item.get('gold', 0)
                reason = item.get('reason', '')
                print(f"    {G}→ {name}{RS} {GY}({gold}g){RS} — {W}{reason}{RS}")

        if getattr(result, 'build_changed', False):
            reason = getattr(result, 'build_change_reason', '')
            print(f"\n  {R}⚠ BUILD CHANGED: {reason}{RS}")

        full_build = getattr(result, 'full_build', [])
        if full_build:
            print(f"\n  {T}📦 FULL BUILD:{RS} {W}{' → '.join(full_build[:6])}{RS}")

        # Solo lane matchup
        laner = getattr(result, 'laner_name', '')
        if laner and not getattr(result, 'is_botlane', False):
            print(f"\n  {R}⚔ VS {laner.upper()}{RS}")

            trade = getattr(result, 'trade_pattern', '')
            if trade:
                print(f"    {GR}Trade: {trade}{RS}")

            punish = getattr(result, 'punish_when', '')
            if punish:
                print(f"    {GR}Punish: {punish}{RS}")

            avoid = getattr(result, 'avoid', '')
            if avoid:
                print(f"    {R}Avoid: {avoid}{RS}")

            cds = getattr(result, 'key_cooldowns', [])
            if cds:
                print(f"    {T}Cooldowns: {', '.join(cds)}{RS}")

            kill = getattr(result, 'kill_window', '')
            if kill:
                print(f"    {G}Kill window: {kill}{RS}")

            wave = getattr(result, 'wave_management', '')
            if wave:
                print(f"    {T}Wave: {wave}{RS}")

        # Bot lane matchup
        if getattr(result, 'is_botlane', False):
            enemy_adc = getattr(result, 'enemy_adc', '')
            enemy_sup = getattr(result, 'enemy_support', '')

            print(f"\n  {R}⚔ BOT LANE: vs {enemy_adc} + {enemy_sup}{RS}")

            # ADC
            if enemy_adc:
                print(f"\n    {R}🎯 {enemy_adc} (ADC){RS}")
                dodge = getattr(result, 'enemy_adc_dodge', '')
                if dodge:
                    print(f"      {R}Dodge: {dodge}{RS}")
                punish = getattr(result, 'enemy_adc_punish', '')
                if punish:
                    print(f"      {GR}Punish: {punish}{RS}")

            # Support
            if enemy_sup:
                print(f"\n    {R}🛡 {enemy_sup} (Support){RS}")
                dodge = getattr(result, 'enemy_support_dodge', '')
                if dodge:
                    print(f"      {R}Dodge: {dodge}{RS}")
                punish = getattr(result, 'enemy_support_punish', '')
                if punish:
                    print(f"      {GR}Punish: {punish}{RS}")

            combo = getattr(result, 'their_kill_combo', '')
            if combo:
                print(f"\n    {R}💀 Their kill combo: {combo}{RS}")

            win = getattr(result, 'your_win_condition', '')
            if win:
                print(f"    {GR}✅ Your win condition: {win}{RS}")

            lvl2 = getattr(result, 'level_2_plan', '')
            if lvl2:
                print(f"    {T}Lvl 2 plan: {lvl2}{RS}")

            bush = getattr(result, 'bush_control', '')
            if bush:
                print(f"    {T}Bush control: {bush}{RS}")

            gank = getattr(result, 'gank_setup', '')
            if gank:
                print(f"    {T}Gank setup: {gank}{RS}")

        # Death review
        death_reason = getattr(result, 'death_reason', '')
        if death_reason:
            count = getattr(result, 'death_count', 0)
            print(f"\n  {R}💀 DEATH #{count}: {death_reason}{RS}")

            fix = getattr(result, 'death_fix', '')
            if fix:
                print(f"    {GR}Fix: {fix}{RS}")

            pos = getattr(result, 'death_positioning', '')
            if pos:
                print(f"    {T}Position: {pos}{RS}")

            recovery = getattr(result, 'death_recovery', '')
            if recovery:
                print(f"    {W}Recovery: {recovery}{RS}")

        # Teamfight
        focus = getattr(result, 'focus_target', '')
        if focus and state in ('in_game_teamfight', 'teamfight_prep'):
            print(f"\n  {R}⚔ TEAMFIGHT{RS}")
            print(f"    {GR}Focus: {focus}{RS}")

            threat = getattr(result, 'biggest_threat', '')
            if threat:
                print(f"    {R}Threat: {threat}{RS}")

            pos = getattr(result, 'positioning', '')
            if pos:
                print(f"    {T}Position: {pos}{RS}")

        # Warnings
        warnings = getattr(result, 'warnings', [])
        for w in warnings:
            print(f"\n  {R}⚠ {w}{RS}")

        print(f"\n{T}{'═' * 60}{RS}")
        print(f"{D}  PrintScreen again anytime for updated coaching{RS}\n")

    def hide(self):
        pass

    def toggle(self):
        pass


# =============================================================================
# GUI OVERLAY (Windows tkinter — transparent, always-on-top)
# =============================================================================

class LiveOverlay:
    """
    Transparent overlay that renders coaching on top of League of Legends.

    Features:
    - Always-on-top with transparency
    - Auto-dismiss timer
    - Draggable
    - F9 toggle visibility
    - Adapts layout based on game state
    - Cyberpunk teal/gold theme
    """

    def __init__(self, width: int = 480, opacity: float = 0.92,
                 position: str = "top-right", duration: float = 20.0):
        self.width = width
        self.opacity = opacity
        self.position = position
        self.duration = duration
        self._root = None
        self._visible = False
        self._dismiss_timer = None
        self._drag_data = {"x": 0, "y": 0}

    def show(self, result: Any):
        """Show the overlay with coaching result."""
        try:
            import tkinter as tk
            from tkinter import font as tkfont
        except ImportError:
            logger.warning("tkinter not available — falling back to console")
            ConsoleOverlay().show(result)
            return

        # Run in a thread so it doesn't block the pipeline
        def _show():
            try:
                self._create_window(result)
            except Exception as e:
                logger.error(f"Overlay error: {e}")
                ConsoleOverlay().show(result)

        thread = threading.Thread(target=_show, daemon=True)
        thread.start()

    def _create_window(self, result: Any):
        """Create the tkinter overlay window."""
        import tkinter as tk

        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass

        root = tk.Tk()
        self._root = root
        root.title("League Coach OS")
        root.configure(bg=Theme.BG)
        root.attributes("-topmost", True)
        root.attributes("-alpha", self.opacity)
        root.overrideredirect(True)

        # Position
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = screen_w - self.width - 20
        y = 60
        root.geometry(f"{self.width}x{screen_h - 120}+{x}+{y}")

        # Make draggable
        root.bind("<Button-1>", self._start_drag)
        root.bind("<B1-Motion>", self._do_drag)
        root.bind("<Escape>", lambda e: self._dismiss())

        # Scrollable canvas
        canvas = tk.Canvas(root, bg=Theme.BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg=Theme.BG)

        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw", width=self.width - 20)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Render content based on game state
        self._render_content(frame, result)

        # Auto-dismiss
        root.after(int(self.duration * 1000), self._dismiss)

        self._visible = True
        root.mainloop()

    def _render_content(self, frame, result: Any):
        """Render coaching content into the frame."""
        import tkinter as tk

        state = getattr(result, 'game_state', 'unknown')
        pad = {"padx": 10, "pady": 2}

        # ── Header ──
        header_frame = tk.Frame(frame, bg=Theme.TEAL, height=3)
        header_frame.pack(fill="x")

        tk.Label(frame, text="⚡ LEAGUE COACH OS", font=(Theme.FONT, 14, "bold"),
                 fg=Theme.TEAL, bg=Theme.BG).pack(**pad, anchor="w")

        phase = getattr(result, 'game_phase', '')
        proc_time = getattr(result, 'processing_time', 0)
        tk.Label(frame, text=f"{state.replace('_', ' ').title()} • {phase} • {proc_time:.1f}s",
                 font=(Theme.FONT, 9), fg=Theme.GRAY, bg=Theme.BG).pack(**pad, anchor="w")

        self._separator(frame)

        # ── Headline ──
        headline = getattr(result, 'headline', '')
        if headline:
            tk.Label(frame, text=headline, font=(Theme.FONT, 12, "bold"),
                     fg=Theme.GOLD, bg=Theme.BG, wraplength=self.width - 40,
                     justify="left").pack(padx=10, pady=6, anchor="w")

        # ── Next 30 Seconds ──
        tips = getattr(result, 'next_30_seconds', [])
        if tips:
            self._section_header(frame, "▸ DO NOW")
            for i, tip in enumerate(tips[:3], 1):
                color = Theme.GREEN if i == 1 else Theme.WHITE
                tk.Label(frame, text=f"  {i}. {tip}", font=(Theme.FONT, 10),
                         fg=color, bg=Theme.BG, wraplength=self.width - 50,
                         justify="left").pack(**pad, anchor="w")

        # ── Build Advice ──
        buy_now = getattr(result, 'buy_now', [])
        if buy_now:
            self._separator(frame)
            self._section_header(frame, "🛒 BUY NOW")
            for item in buy_now:
                name = item.get('item', '?')
                gold = item.get('gold', 0)
                reason = item.get('reason', '')
                item_frame = tk.Frame(frame, bg=Theme.BG_SECTION)
                item_frame.pack(fill="x", padx=8, pady=2)
                tk.Label(item_frame, text=f"→ {name}", font=(Theme.FONT, 10, "bold"),
                         fg=Theme.GOLD, bg=Theme.BG_SECTION).pack(side="left", padx=4)
                tk.Label(item_frame, text=f"({gold}g)", font=(Theme.FONT, 9),
                         fg=Theme.GRAY, bg=Theme.BG_SECTION).pack(side="left")
                tk.Label(item_frame, text=f" {reason}", font=(Theme.FONT, 9),
                         fg=Theme.WHITE, bg=Theme.BG_SECTION, wraplength=280,
                         justify="left").pack(side="left", padx=4)

        if getattr(result, 'build_changed', False):
            reason = getattr(result, 'build_change_reason', '')
            tk.Label(frame, text=f"⚠ BUILD CHANGED: {reason}", font=(Theme.FONT, 9, "bold"),
                     fg=Theme.ORANGE, bg=Theme.BG, wraplength=self.width - 40,
                     justify="left").pack(padx=10, pady=4, anchor="w")

        full_build = getattr(result, 'full_build', [])
        if full_build:
            build_text = " → ".join(full_build[:6])
            tk.Label(frame, text=f"📦 {build_text}", font=(Theme.FONT_MONO, 8),
                     fg=Theme.TEAL, bg=Theme.BG, wraplength=self.width - 40,
                     justify="left").pack(padx=10, pady=2, anchor="w")

        # ── Solo Lane Matchup ──
        laner = getattr(result, 'laner_name', '')
        if laner and not getattr(result, 'is_botlane', False):
            self._separator(frame)
            self._section_header(frame, f"⚔ VS {laner.upper()}")

            self._matchup_row(frame, "Trade", getattr(result, 'trade_pattern', ''), Theme.GREEN)
            self._matchup_row(frame, "Punish", getattr(result, 'punish_when', ''), Theme.GREEN)
            self._matchup_row(frame, "Avoid", getattr(result, 'avoid', ''), Theme.RED)
            self._matchup_row(frame, "Kill window", getattr(result, 'kill_window', ''), Theme.GOLD)
            self._matchup_row(frame, "Wave", getattr(result, 'wave_management', ''), Theme.TEAL)

            cds = getattr(result, 'key_cooldowns', [])
            if cds:
                self._matchup_row(frame, "Cooldowns", ", ".join(cds), Theme.TEAL)

        # ── Bot Lane Matchup ──
        if getattr(result, 'is_botlane', False):
            self._separator(frame)
            enemy_adc = getattr(result, 'enemy_adc', '?')
            enemy_sup = getattr(result, 'enemy_support', '?')
            self._section_header(frame, f"⚔ BOT: vs {enemy_adc} + {enemy_sup}")

            # Enemy ADC
            self._subsection(frame, f"🎯 {enemy_adc} (ADC)", Theme.RED)
            self._matchup_row(frame, "Dodge", getattr(result, 'enemy_adc_dodge', ''), Theme.RED)
            self._matchup_row(frame, "Punish", getattr(result, 'enemy_adc_punish', ''), Theme.GREEN)

            # Enemy Support
            self._subsection(frame, f"🛡 {enemy_sup} (Support)", Theme.RED)
            self._matchup_row(frame, "Dodge", getattr(result, 'enemy_support_dodge', ''), Theme.RED)
            self._matchup_row(frame, "Punish", getattr(result, 'enemy_support_punish', ''), Theme.GREEN)

            # Combined
            self._matchup_row(frame, "Their kill combo", getattr(result, 'their_kill_combo', ''), Theme.RED)
            self._matchup_row(frame, "Your win con", getattr(result, 'your_win_condition', ''), Theme.GREEN)
            self._matchup_row(frame, "Level 2 plan", getattr(result, 'level_2_plan', ''), Theme.TEAL)
            self._matchup_row(frame, "Bush control", getattr(result, 'bush_control', ''), Theme.TEAL)
            self._matchup_row(frame, "Gank setup", getattr(result, 'gank_setup', ''), Theme.BLUE)

        # ── Death Review ──
        death_reason = getattr(result, 'death_reason', '')
        if death_reason:
            self._separator(frame)
            count = getattr(result, 'death_count', 0)
            self._section_header(frame, f"💀 DEATH #{count}")

            tk.Label(frame, text=death_reason, font=(Theme.FONT, 10, "bold"),
                     fg=Theme.RED, bg=Theme.BG, wraplength=self.width - 40,
                     justify="left").pack(padx=12, pady=2, anchor="w")

            self._matchup_row(frame, "Fix", getattr(result, 'death_fix', ''), Theme.GREEN)
            self._matchup_row(frame, "Position", getattr(result, 'death_positioning', ''), Theme.TEAL)
            self._matchup_row(frame, "Recovery", getattr(result, 'death_recovery', ''), Theme.WHITE)

        # ── Teamfight ──
        focus = getattr(result, 'focus_target', '')
        if focus and getattr(result, 'game_state', '') in ('in_game_teamfight', 'teamfight_prep',
                                                             'mid_game', 'late_game'):
            self._separator(frame)
            self._section_header(frame, "⚔ TEAMFIGHT")
            self._matchup_row(frame, "Focus", focus, Theme.GREEN)
            self._matchup_row(frame, "Threat", getattr(result, 'biggest_threat', ''), Theme.RED)
            self._matchup_row(frame, "Position", getattr(result, 'positioning', ''), Theme.TEAL)

        # ── Warnings ──
        warnings = getattr(result, 'warnings', [])
        if warnings:
            self._separator(frame)
            for w in warnings:
                tk.Label(frame, text=f"⚠ {w}", font=(Theme.FONT, 9, "bold"),
                         fg=Theme.ORANGE, bg=Theme.BG, wraplength=self.width - 40,
                         justify="left").pack(padx=10, pady=2, anchor="w")

        # ── Footer ──
        self._separator(frame)
        tk.Label(frame, text="PrintScreen again anytime • ESC to close • F9 to toggle",
                 font=(Theme.FONT, 8), fg=Theme.DARK_GRAY, bg=Theme.BG).pack(pady=4)

    # ── Rendering helpers ──

    def _separator(self, frame):
        import tkinter as tk
        tk.Frame(frame, bg=Theme.DARK_GRAY, height=1).pack(fill="x", padx=8, pady=4)

    def _section_header(self, frame, text: str):
        import tkinter as tk
        tk.Label(frame, text=text, font=(Theme.FONT, 11, "bold"),
                 fg=Theme.TEAL, bg=Theme.BG).pack(padx=10, pady=(4, 2), anchor="w")

    def _subsection(self, frame, text: str, color: str = Theme.WHITE):
        import tkinter as tk
        tk.Label(frame, text=text, font=(Theme.FONT, 10, "bold"),
                 fg=color, bg=Theme.BG).pack(padx=14, pady=(4, 1), anchor="w")

    def _matchup_row(self, frame, label: str, value: str, color: str = Theme.WHITE):
        if not value:
            return
        import tkinter as tk
        row = tk.Frame(frame, bg=Theme.BG)
        row.pack(fill="x", padx=12, pady=1)
        tk.Label(row, text=f"{label}:", font=(Theme.FONT, 9, "bold"),
                 fg=Theme.GRAY, bg=Theme.BG).pack(side="left")
        tk.Label(row, text=f" {value}", font=(Theme.FONT, 9),
                 fg=color, bg=Theme.BG, wraplength=self.width - 120,
                 justify="left").pack(side="left", fill="x")

    def _start_drag(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _do_drag(self, event):
        if self._root:
            x = self._root.winfo_x() + event.x - self._drag_data["x"]
            y = self._root.winfo_y() + event.y - self._drag_data["y"]
            self._root.geometry(f"+{x}+{y}")

    def _dismiss(self):
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None
            self._visible = False

    def hide(self):
        self._dismiss()

    def toggle(self):
        if self._visible:
            self.hide()
        # Can't re-show without new data — user needs to PrintScreen again
