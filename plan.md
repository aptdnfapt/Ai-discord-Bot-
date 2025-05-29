# Discord AI Bot with Gemini API

This document outlines the features of a Discord bot powered by the Gemini API.

## Core Idea
A versatile Discord bot that leverages the Gemini API for intelligent responses. It can be configured for specific topics via a system prompt and interacts through dedicated channels or keyword triggers.

## Current Implemented Features:

1.  **Gemini API Integration:**
    *   The bot utilizes Google's Gemini API for generating AI responses.
    *   API Key and Model Name (`GEMINI_MODEL_NAME`) are configurable via the `.env` file.

2.  **System Prompt & Persona:**
    *   A `SYSTEM_PROMPT` can be set in the `.env` file to define the bot's base persona, expertise, or topic focus.

3.  **Configurable Command Prefix:**
    *   The `COMMAND_PREFIX` (e.g., `$`, `!!`) is configurable in the `.env` file.

4.  **Dual Interaction Modes:**
    *   **Set Channels (`$setchannel`, `$unsetchannel`):**
        *   Ability to designate specific channels where the bot responds to every message.
        *   Supports multiple set channels per server.
        *   Maintains a shared conversation history (`main_chat_history`) for these channels within each server.
    *   **Keyword-Based Replies:**
        *   The bot monitors messages in all accessible channels (unless ignored) for `BOT_KEYWORDS` (configurable in `.env`).
        *   Replies to messages containing these keywords, using user-specific conversation history (`rolling_history`).
        *   The `$ignore` and `$unignore` commands allow per-channel control over keyword detection.

5.  **Customizable AI Contexts:**
    *   The bot can load custom system prompts from `.txt` files located in a configurable `CONTEXT_DIR` (default: `context/`).
    *   The `$setcontext <context_name>` command allows setting a specific loaded context for a channel. This context will override the default `SYSTEM_PROMPT` for all AI interactions in that channel.
    *   The `$unsetcontext` command removes the custom context, reverting to the default `SYSTEM_PROMPT`.
    *   Contexts are stored persistently in `bot_data.json` on a per-channel basis (`channel_active_contexts`).

6.  **Context Awareness & Persistence:**
    *   Conversation history and settings are stored in `bot_data.json` to persist across restarts.
    *   **History Management:**
        *   User-specific `rolling_history` (for keyword replies) is maintained using a FIFO (First-In, First-Out) mechanism, keeping approximately the last 100 entries (50 user/bot message pairs).
        *   Server-wide `main_chat_history` (for set channels) also uses FIFO, keeping approximately the last 200 entries (100 user/bot message pairs).
    *   Set channel IDs, ignored channel IDs, and active channel contexts are stored persistently.

7.  **Utility Commands:**
    *   `$time`: Shows the system uptime of the VPS/machine hosting the bot.
    *   `$help`: A custom help command listing available commands.

8.  **Rate Limiting:**
    *   A universal rate limit applies to all AI prompt generations (both keyword and set channel interactions) per user.
    *   `RATE_LIMIT_MAX_PROMPTS` and `RATE_LIMIT_SECONDS` are configurable in the `.env` file.
    *   The bot notifies users when they are rate-limited.

9.  **Configuration via `.env`:**
    *   `DISCORD_TOKEN`, `GEMINI_API_KEY`, `COMMAND_PREFIX`
    *   `BOT_KEYWORDS`, `GEMINI_MODEL_NAME`, `SYSTEM_PROMPT`
    *   `CONTEXT_DIR`
    *   `RATE_LIMIT_MAX_PROMPTS`, `RATE_LIMIT_SECONDS`

## Future Enhancements (Planned):

1.  **Automatic User Profile Summary Generation:**
    *   Implement logic to periodically use the Gemini API to summarize a user's `rolling_history`.
    *   Store this summary in the `profile_summary` field within `user_specific_context` in `bot_data.json`.
    *   This summary will then be used to provide more personalized and long-term context for keyword-triggered replies.
