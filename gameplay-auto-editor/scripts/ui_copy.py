"""User-facing copy and label maps for the desktop app (UX microcopy)."""

from __future__ import annotations

APP_DISPLAY_NAME = "Gameplay Auto Editor"

# Outcome-focused hero & guidance
HERO_HEADLINE = "Turn your best moments into share-ready clips"
HERO_SUBLINE = "Pick a gameplay video, create vertical highlights, then review and post."
STEP_PICK = "Pick video"
STEP_CREATE = "Create clips"
STEP_REVIEW = "Review & share"

STATUS_IDLE = "Start by selecting a gameplay video."
STATUS_VIDEO_SELECTED = "Looking good — ready when you are."
STATUS_CREATING = "Creating your clips…"
STATUS_DONE = "Your clips are ready to review."
STATUS_FAILED = "Something went wrong — check the log below."

# Primary actions (verb + outcome)
BTN_SELECT_VIDEO = "Select gameplay video"
BTN_ADD_QUEUE = "Add to batch"
BTN_CLEAR_QUEUE = "Clear batch"
BTN_CREATE_CLIPS = "Create my clips"
BTN_CREATING_CLIPS = "Creating clips…"
BTN_OPEN_FOLDER = "Open clips folder"
BTN_SAVE_ALL = "Save all clips"
BTN_COPY_CAPTIONS = "Copy all captions"

# Sections
SECTION_SOURCE = "Source video"
SECTION_CLIP_SETTINGS = "Clip settings"
SECTION_ACTIONS = "Create & export"
SECTION_CREATE = "Create clips"
SECTION_EXPORT = "Review & export"
SECTION_TOOLS = "Tools & integrations"
SECTION_CREATING = "Creating your clips"
SECTION_YOUR_CLIPS = "Your clips"
SECTION_EMPTY_CLIPS = "Your finished clips will show up here after you create them."
EMPTY_STATE_TITLE = "No clips yet"
EMPTY_STATE_HINT = "Each finished clip includes Play, Save, Copy caption, and optional social post actions."
LOADING_CLIPS = "Finding your best moments and building share-ready clips…"
SECTION_ADVANCED = "Advanced options"
BTN_SHOW_ADVANCED = "Show advanced options"
BTN_HIDE_ADVANCED = "Hide advanced options"
BTN_SHOW_INTEGRATIONS = "Show tools & connect"
BTN_HIDE_INTEGRATIONS = "Hide tools & connect"

# Settings labels (plain language)
LBL_DETECTION = "Highlight finder"
LBL_CLIP_COUNT = "How many clips"
LBL_SENSITIVITY = "Highlight bar"
LBL_EXPORT_FOR = "Made for"
LBL_LOOK = "Caption style"
LBL_GAME = "Game type"
LBL_FACECAM = "Face cam split"
LBL_SCAN_EVERY = "Sample interval (sec)"
LBL_AI_FRAMES = "Max samples"
LBL_ROLLOUT_PHASE = "Quality rollout"
LBL_CLIP_PROMPT = "Clip focus (optional)"

BTN_CANCEL = "Cancel"
BTN_CANCELLING = "Cancelling…"

ROLLOUT_PHASE_LABEL_TO_VALUE = {
    "Stable (proven defaults)": "stable",
    "Phase 1 · Visual polish": "phase_1",
    "Phase 2 · Smarter clips": "phase_2",
    "Phase 3 · Full quality": "phase_3",
    "Phase 4 · Performance & control": "phase_4",
    "Custom (config.json)": "custom",
}
ROLLOUT_PHASE_VALUE_TO_LABEL = {value: label for label, value in ROLLOUT_PHASE_LABEL_TO_VALUE.items()}

DETECTION_LABEL_TO_VALUE = {
    "Fast (no API key)": "heuristic",
    "Smart auto": "auto",
    "OpenAI vision": "openai",
    "Claude vision": "anthropic",
}
DETECTION_VALUE_TO_LABEL = {value: label for label, value in DETECTION_LABEL_TO_VALUE.items()}

PLATFORM_LABEL_TO_VALUE = {
    "Any platform": "generic",
    "TikTok": "tiktok",
    "YouTube Shorts": "youtube_shorts",
    "Instagram Reels": "instagram_reels",
}
PLATFORM_VALUE_TO_LABEL = {value: label for label, value in PLATFORM_LABEL_TO_VALUE.items()}

GAME_LABEL_TO_VALUE = {
    "Any game": "generic",
    "Valorant": "valorant",
    "Call of Duty": "cod",
    "Fortnite": "fortnite",
}
GAME_VALUE_TO_LABEL = {value: label for label, value in GAME_LABEL_TO_VALUE.items()}

THEME_LABEL_TO_VALUE = {
    "Classic": "default",
    "Bold hooks": "hormozi",
    "Minimal": "minimal",
    "Gen Z": "gen_z",
}
THEME_VALUE_TO_LABEL = {value: label for label, value in THEME_LABEL_TO_VALUE.items()}

REFRAME_LABEL_TO_VALUE = {"Off": "off", "On": "on"}
REFRAME_VALUE_TO_LABEL = {value: label for label, value in REFRAME_LABEL_TO_VALUE.items()}

# Assistant panel
ASSISTANT_TITLE = "Clip assistant"
ASSISTANT_TAGLINE = "Tips on your clips, setup, and posting"
BTN_HIDE_ASSISTANT = "Hide assistant"
BTN_SHOW_ASSISTANT = "Show assistant"
ASSISTANT_WELCOME = "Hi! Ask me why a clip was picked, how to improve settings, or where to post."
ASSISTANT_PLACEHOLDER = "Ask about your clips…"
BTN_ASK = "Ask"
BTN_CLEAR_CHAT = "Clear chat"
CHIP_EXPLAIN = "Why these clips?"
CHIP_SETUP = "Help me set up"
CHIP_SETTINGS = "Improve settings"
CHIP_POST = "Posting tips"

# Integrations tabs
TAB_SHARE = "Share online"
TAB_SMARTER = "Smarter detection"
TAB_KILLFEED = "Killfeed reader"
TAB_SHARE_HELP = "Connect YouTube, TikTok, or Instagram to post clips. Your login stays secure on this device."
LBL_CHAT_LOG = "Chat log (optional, Phase 3)"
BTN_BROWSE_CHAT_LOG = "Browse chat log"
BTN_SAVE_CHAT_LOG = "Save chat path"
BTN_CLEAR_CHAT_LOG = "Clear"
MSG_CHAT_LOG_SAVED = "Chat log path saved. Chat spike scoring is active for the next run."
MSG_CHAT_LOG_CLEARED = "Chat log cleared. Other Phase 3 features remain active."

# Clip card actions
BTN_PLAY = "Play"
BTN_FOLDER = "Folder"
BTN_SAVE_ONE = "Save copy"
BTN_COPY_ONE = "Copy caption"
BTN_COPY_SOCIAL = "Copy post text"
BTN_POST = "Post to"
BTN_FRAME = "Preview"

# Messages
MSG_PICK_VIDEO_FIRST = "Select a gameplay video first."
MSG_FFMPEG_MISSING = (
    "FFmpeg is required to create clips.\n\n"
    "Install FFmpeg, then reopen the app."
)
MSG_NO_CLIPS_YET = "Create clips first, then they'll appear here."
MSG_RENDER_FAILED = (
    "We found highlight moments but couldn't finish rendering. "
    "Open the activity log below for FFmpeg details."
)
MSG_CAPTIONS_COPIED = "Captions copied to clipboard."
MSG_CLIP_READY = "No video selected yet"
