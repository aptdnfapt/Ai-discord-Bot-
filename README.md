# Discord AI Bot with Gemini

This is a Python-based Discord bot that uses Google's Gemini API to provide AI-powered responses. It can be configured to interact in specific channels continuously or respond to keywords in other channels.

## Features

*   **Configurable Command Prefix:** Change the bot's command prefix (e.g., `$` to `!!`).
*   **Gemini API Integration:** Leverages Google's Gemini models for generating responses.
*   **Contextual Conversations:**
    *   **Set Channels:** Designate specific channels where the bot will respond to every message, maintaining a conversation history for that channel.
    *   **Keyword Replies:** Responds to messages containing specific keywords (e.g., "ai", "bot", its own name) in any channel (unless ignored), using user-specific conversation history.
*   **Persistent Data:** Saves channel settings, conversation histories, and user contexts to a JSON file (`bot_data.json`).
*   **Channel Management:**
    *   `setchannel`/`unsetchannel`: Manage channels for continuous conversation.
    *   `ignore`/`unignore`: Control where keyword-based replies are active.
*   **Rate Limiting:** Prevents spamming AI responses (both keyword and set channel triggers) and warns users when they exceed limits. Configurable via `.env` file.
*   **Customizable Persona:** Define the bot's core behavior and topic expertise via a system prompt in the `.env` file.
*   **Utility Commands:** Includes `help` and `time` (system uptime).

## Prerequisites

*   Python 3.8 or higher
*   `pip` (Python package installer)
*   A Discord Bot Token
*   A Google Gemini API Key

## Setup Instructions

1.  **Clone or Download the Repository:**
    ```bash
    # If using git
    git clone <repository_url>
    cd <repository_directory>
    ```
    If you downloaded a ZIP, extract it and navigate into the directory.

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install  discord.py python-dotenv google-generativeai
    ```
4.  **Configure Environment Variables:**
    Create a `.env` file in the root directory of the project and populate it with your credentials and desired settings. Use the provided `.env` file in the chat as a template:

    ```dotenv
    DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
    GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
    COMMAND_PREFIX=$
    BOT_KEYWORDS=ai,bot,assistant,your_bot_name # Comma-separated list of keywords
    GEMINI_MODEL_NAME=gemini-1.5-flash          # e.g., gemini-pro, gemini-1.0-pro, gemini-1.5-flash
    SYSTEM_PROMPT="You are a helpful AI assistant. Your primary topic is general knowledge but you adapt based on context."

    # Rate Limiting for AI Responses
    RATE_LIMIT_MAX_PROMPTS=3 # Max number of AI prompts allowed within the time window per user
    RATE_LIMIT_SECONDS=8     # Time window in seconds for the rate limit
    ```

    *   **`DISCORD_TOKEN`**: Your Discord bot's token. (Obtain from the Discord Developer Portal)
    *   **`GEMINI_API_KEY`**: Your API key for Google Gemini. (Obtain from Google AI Studio)
    *   **`COMMAND_PREFIX`**: The prefix for bot commands (e.g., `$`, `!`, `!!`).
    *   **`BOT_KEYWORDS`**: Comma-separated list of words that will trigger the bot in non-set channels. The bot's actual name will also be added to this list automatically when it starts.
    *   **`GEMINI_MODEL_NAME`**: The specific Gemini model you want to use (e.g., `gemini-pro`, `gemini-1.5-flash`).
    *   **`SYSTEM_PROMPT`**: The initial instruction given to the AI to define its persona and general behavior.
    *   **`RATE_LIMIT_MAX_PROMPTS`**: The maximum number of AI prompts a user is allowed to make within the `RATE_LIMIT_SECONDS` window. Defaults to `3` if not set.
    *   **`RATE_LIMIT_SECONDS`**: The time window in seconds for the rate limit. Defaults to `8` if not set.

5.  **Run the Bot:**
    ```bash
    python bot.py
    ```
    You should see log messages in your console indicating the bot has connected to Discord and the Gemini API is configured.

## Bot Usage

### How the Bot Interacts

*   **Set Channels:** If you use the `{COMMAND_PREFIX}setchannel` command in a channel, the bot will respond to *every* message sent in that channel. It maintains a shared conversation history for this channel.
*   **Keyword Replies:** In any other channel (that is not explicitly ignored using `{COMMAND_PREFIX}ignore`), the bot will listen for messages containing any of the defined `BOT_KEYWORDS` (or its own name). If a keyword is detected, it will generate a response using a conversation history specific to the user who triggered it.
*   **Rate Limit Notifications:** If a user triggers AI responses too frequently (either via keywords or in a set channel), they will be temporarily rate-limited and notified by the bot.
*   **Commands:** Messages starting with the `COMMAND_PREFIX` are treated as commands.

### Available Commands

(Replace `{COMMAND_PREFIX}` with the prefix you set in your `.env` file, e.g., `$`)

*   **`{COMMAND_PREFIX}help`**:
    *   Shows a help message listing all available commands and their usage.

*   **`{COMMAND_PREFIX}setchannel`**:
    *   Sets the current channel for continuous conversation. The bot will respond to all messages in this channel.
    *   Usage: `{COMMAND_PREFIX}setchannel`

*   **`{COMMAND_PREFIX}unsetchannel`**:
    *   Unsets the current channel from continuous conversation. The bot will no longer respond to every message here (but keyword replies might still work).
    *   Usage: `{COMMAND_PREFIX}unsetchannel`

*   **`{COMMAND_PREFIX}ignore`**:
    *   Disables keyword-triggered replies in the current channel. The bot will not respond to keywords in this channel.
    *   Usage: `{COMMAND_PREFIX}ignore`

*   **`{COMMAND_PREFIX}unignore`**:
    *   Enables keyword-triggered replies in the current channel (if they were previously disabled).
    *   Usage: `{COMMAND_PREFIX}unignore`

*   **`{COMMAND_PREFIX}time`**:
    *   Shows the system uptime of the server where the bot is hosted.
    *   Usage: `{COMMAND_PREFIX}time`

## Data Storage

*   The bot stores its configuration (set channels, ignored channels) and conversation histories in a file named `bot_data.json`.
*   This file is created automatically if it doesn't exist.
*   User-specific conversation history for keyword replies is stored under `user_specific_context`.
*   Channel-specific conversation history for "set channels" is stored under `main_chat_history`.

## Troubleshooting

*   **"DISCORD_TOKEN not found" or "Invalid Discord token"**: Ensure your `.env` file is correctly named, in the root project directory, and contains the correct `DISCORD_TOKEN`.
*   **"GEMINI_API_KEY not found"**: Ensure your `.env` file has the `GEMINI_API_KEY` set correctly.
*   **"Failed to configure Gemini API or model"**: Double-check your `GEMINI_API_KEY` and `GEMINI_MODEL_NAME` in the `.env` file. Ensure the model name is valid for the Gemini API.
*   **Bot not responding**:
    *   Check the console logs for any errors.
    *   Ensure the bot has the necessary permissions in your Discord server (Read Messages, Send Messages, View Channels).
    *   Verify the `COMMAND_PREFIX` and `BOT_KEYWORDS` in your `.env` file.
*   **Permissions Error for `uptime` command**: The system running the bot might not have the `uptime` command available or accessible.

## Contributing

Feel free to fork the repository, make improvements, and submit pull requests.
