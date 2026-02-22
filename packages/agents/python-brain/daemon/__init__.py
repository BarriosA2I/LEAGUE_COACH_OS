# Daemon package
from daemon.screenshot_watcher import LeagueCoachDaemon, DaemonConfig
from daemon.game_state_detector import GameStateDetector, GameState, GamePhase, GameSession
from daemon.live_pipeline import LiveCoachingPipeline, CoachingResult, LivePipelineConfig
from daemon.live_overlay import LiveOverlay, ConsoleOverlay as LiveConsoleOverlay
from daemon.chat_bubble import ChatSession, ChatMessage, ChatBubbleIntegration
