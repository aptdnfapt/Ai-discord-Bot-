import os
import json
import discord
from discord.ext import commands
from dotenv import load_dotenv
import subprocess
import time
import logging
import google.generativeai as genai # Ensure this import is active

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "$") # Default to '$' if not set

# New environment variables for Gemini and Keywords
BOT_KEYWORDS_STR = os.getenv("BOT_KEYWORDS", "ai,bot,assistant")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-pro") # Default to gemini-pro
DEFAULT_SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful AI assistant.")

# New environment variables for Rate Limiting
RATE_LIMIT_MAX_PROMPTS = int(os.getenv("RATE_LIMIT_MAX_PROMPTS", 3)) # Default to 3 prompts
RATE_LIMIT_SECONDS = int(os.getenv("RATE_LIMIT_SECONDS", 8))     # Default to 8 seconds

# Parse BOT_KEYWORDS_STR into a list. This will be finalized in on_ready.
KEYWORDS = [keyword.strip().lower() for keyword in BOT_KEYWORDS_STR.split(',')]

# Initialize Discord Bot with intents
# It's crucial to enable necessary intents for your bot to receive events.
# discord.Intents.all() is broad; consider using more specific intents for production.
intents = discord.Intents.default()
intents.message_content = True # Required to read message content
intents.members = True # Required for on_member_join, etc., if you add those features
intents.guilds = True # Required for guild-related events

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)


# --- Gemini API Configuration ---
model = None # Initialize model to None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL_NAME) # Use the loaded model name
        logging.info(f"Gemini API configured with model: {GEMINI_MODEL_NAME}")
    except Exception as e:
        logging.error(f"Failed to configure Gemini API or model: {e}")
        # model will remain None, get_gemini_response will handle this
else:
    logging.warning("GEMINI_API_KEY not found in .env. Gemini features will be disabled.")
    # model will remain None

# Data persistence setup
DATA_FILE = "bot_data.json"
bot_data = {} # This will hold the loaded data
user_prompt_timestamps = {} # Transient state for rate limiting, renamed from keyword_trigger_timestamps

# --- Helper functions for data persistence ---
def load_data():
    """Loads bot data from the JSON file."""
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            logging.info(f"Loaded data from {DATA_FILE}")
            return data
    except FileNotFoundError:
        logging.warning(f"{DATA_FILE} not found. Initializing with empty data.")
        return {} # Return an empty dict if file not found
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from {DATA_FILE}. File might be corrupted. Initializing with empty data.")
        return {} # Return an empty dict if JSON is invalid

def save_data(data):
    """Saves bot data to the JSON file."""
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
            logging.info(f"Saved data to {DATA_FILE}")
    except IOError as e:
        logging.error(f"Error saving data to {DATA_FILE}: {e}")

# Load data at startup
bot_data = load_data()

# --- Helper functions for data structure management ---
def ensure_server_data(server_id_str):
    """Ensures the server's data structure exists in bot_data."""
    if server_id_str not in bot_data:
        bot_data[server_id_str] = {
            "set_channels": [],
            "main_chat_history": [],
            "ignored_channels_for_keywords": [],
            "user_specific_context": {}
        }
        logging.info(f"Initialized data structure for server: {server_id_str}")
        save_data(bot_data) # Save immediately after creating new server entry

def ensure_user_data(server_id_str, user_id_str):
    """Ensures the user's data structure exists within a server's data."""
    ensure_server_data(server_id_str) # Ensure server data exists first
    if user_id_str not in bot_data[server_id_str]["user_specific_context"]:
        bot_data[server_id_str]["user_specific_context"][user_id_str] = {
            "rolling_history": [],
            "profile_summary": ""
        }
        logging.info(f"Initialized user context for user: {user_id_str} in server: {server_id_str}")
        save_data(bot_data) # Save immediately after creating new user entry

# --- Centralized Rate Limiting Function ---
def check_and_update_rate_limit(user_id: str, server_id: str) -> bool:
    """
    Checks if a user is rate-limited for AI prompts and updates their timestamp.
    Returns True if the user is NOT rate-limited and the prompt can proceed, False otherwise.
    """
    current_time = time.time()

    if server_id not in user_prompt_timestamps:
        user_prompt_timestamps[server_id] = {}
    if user_id not in user_prompt_timestamps[server_id]:
        user_prompt_timestamps[server_id][user_id] = []

    user_timestamps = user_prompt_timestamps[server_id][user_id]
    # Filter out old timestamps
    user_timestamps = [ts for ts in user_timestamps if current_time - ts < RATE_LIMIT_SECONDS]

    if len(user_timestamps) >= RATE_LIMIT_MAX_PROMPTS:
        logging.info(f"User {user_id} in server {server_id} rate limited for AI prompts.")
        return False # Rate limited

    user_timestamps.append(current_time)
    user_prompt_timestamps[server_id][user_id] = user_timestamps
    return True # Not rate limited, prompt can proceed

# --- Placeholder for Gemini API Interaction ---
async def get_gemini_response(prompt_history, current_message_content, system_prompt_override=None):
    """
    Interacts with the Gemini API.
    Uses DEFAULT_SYSTEM_PROMPT unless a system_prompt_override is provided.
    """
    if not model: # Check if the global 'model' object was successfully initialized
        logging.warning("Gemini model not available. Returning placeholder.")
        return "My AI capabilities are currently disabled (model not loaded)."

    # Determine the system prompt to use
    active_system_prompt = system_prompt_override if system_prompt_override else DEFAULT_SYSTEM_PROMPT
    
    # The 'active_system_prompt' is conceptually used. For some Gemini models/setups,
    # system instructions are part of the model configuration or the initial turns of history.
    # For `start_chat`, the history is primary. We'll log the conceptual prompt.
    logging.info(f"Conceptual system context for Gemini: '{active_system_prompt}'")
    logging.debug(f"Sending to Gemini - History: {prompt_history}, Current: {current_message_content}")

    try:
        # Ensure the model object from global scope is used
        chat_session = model.start_chat(history=prompt_history) # prompt_history should be correctly formatted
        response = await chat_session.send_message_async(current_message_content)
        
        if response and response.text:
            logging.info("Received response from Gemini.")
            return response.text
        else:
            logging.warning("Gemini returned an empty or invalid response.")
            if response and response.prompt_feedback: # Check for safety feedback
                logging.warning(f"Gemini prompt feedback: {response.prompt_feedback}")
                if response.prompt_feedback.block_reason:
                     return f"My safety filters prevented a response: {response.prompt_feedback.block_reason_message or response.prompt_feedback.block_reason}"
            return "I received that, but I don't have a specific response right now."
    except Exception as e:
        logging.error(f"Gemini API error: {e}")
        # from google.generativeai.types import BlockedPromptException # Specific exception for safety
        # if isinstance(e, BlockedPromptException):
        #    return "My safety filters prevented me from responding to that. Please try rephrasing."
        return "Oops! I encountered an error trying to process that with my AI. Please try again later."

# --- Bot Events ---
@bot.event
async def on_ready():
    """Logs when the bot is ready and connected to Discord."""
    global KEYWORDS # Declare KEYWORDS as global to modify it
    if bot.user and bot.user.name.lower() not in KEYWORDS:
        KEYWORDS.append(bot.user.name.lower())
    
    logging.info(f'{bot.user} has connected to Discord!')
    logging.info(f'Command Prefix: {COMMAND_PREFIX}')
    logging.info(f'Keywords: {KEYWORDS}') # Log the finalized keywords
    logging.info(f'Gemini Model: {GEMINI_MODEL_NAME if model else "Not loaded/configured"}')
    logging.info(f'Default System Prompt: "{DEFAULT_SYSTEM_PROMPT}"')
    logging.info(f'AI Rate Limit: {RATE_LIMIT_MAX_PROMPTS} prompts per {RATE_LIMIT_SECONDS} seconds per user.')
    
    print(f'{bot.user} has connected to Discord!')
    print(f'Command Prefix: {COMMAND_PREFIX}')
    print(f'Keywords: {KEYWORDS}')

@bot.event
async def on_message(message):
    """Processes incoming messages for commands, keywords, and set channels."""
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Ensure message is from a guild (not a DM)
    if not message.guild:
        await message.channel.send("I currently only operate in server channels, not DMs.")
        return

    server_id = str(message.guild.id)
    channel_id = message.channel.id
    user_id = str(message.author.id)
    message_content = message.content.lower()

    # Ensure server and user data structures exist
    ensure_server_data(server_id)
    ensure_user_data(server_id, user_id)

    # --- Command Processing ---
    # Let the commands.Bot handle commands first.
    # If a message is a command, process_commands will handle it,
    # and we should return to prevent further processing as a regular message.
    if message.content.startswith(COMMAND_PREFIX):
        await bot.process_commands(message)
        return # Command handled, stop further processing

    # --- Keyword Detection Logic ---
    ignored_channels = bot_data[server_id]["ignored_channels_for_keywords"]

    is_keyword_triggered = any(keyword in message_content for keyword in KEYWORDS)

    if is_keyword_triggered and channel_id not in ignored_channels:
        # Apply Rate Limiting for Keyword Triggers
        if not check_and_update_rate_limit(user_id, server_id):
            await message.channel.send(f"{message.author.mention}, you're asking for AI responses a bit too quickly! Please wait a moment.")
            return # Do not process this keyword trigger

        # Process with Gemini for keyword trigger (user-specific context)
        user_context = bot_data[server_id]["user_specific_context"][user_id]
        rolling_history = user_context["rolling_history"]
        profile_summary = user_context["profile_summary"]

        # Construct prompt for Gemini (adjust format for actual Gemini API)
        # For Gemini, history is a list of {"role": "user/model", "parts": ["text"]}
        gemini_history = rolling_history # Assuming rolling_history is already in Gemini format
        
        # Use DEFAULT_SYSTEM_PROMPT, potentially augmented by profile_summary for keyword interactions
        keyword_system_prompt_override = DEFAULT_SYSTEM_PROMPT
        if profile_summary: # Augment if profile summary exists
             keyword_system_prompt_override += f"\n\nUser profile context: {profile_summary}"

        try:
            # Pass the potentially augmented system prompt to get_gemini_response
            response_text = await get_gemini_response(gemini_history, message.content, system_prompt_override=keyword_system_prompt_override)
            await message.channel.send(response_text)

            # Update rolling history (FIFO)
            rolling_history.append({"role": "user", "parts": [message.content]})
            rolling_history.append({"role": "model", "parts": [response_text]})
            if len(rolling_history) > 100: # Keep last 100 entries
                rolling_history.pop(0)
                rolling_history.pop(0) # Remove both user and model parts

            # Profile Summary Update (Advanced - periodic summarization)
            # if len(rolling_history) % 50 == 0 and len(rolling_history) > 0:
            #     # Trigger a summarization of recent history and update profile_summary
            #     # This would involve another Gemini call
            #     pass

            save_data(bot_data)
            logging.info(f"Keyword triggered response sent in channel {channel_id} for user {user_id}.")
        except Exception as e:
            logging.error(f"Error during keyword-triggered Gemini interaction: {e}")
            await message.channel.send("Sorry, I couldn't process that keyword request right now.")
        return # Keyword interaction handled, stop further processing

    # --- Set Channel Interaction Logic ---
    set_channels = bot_data[server_id]["set_channels"]
    if channel_id in set_channels:
        # Apply Rate Limiting for Set Channel Triggers
        if not check_and_update_rate_limit(user_id, server_id):
            await message.channel.send(f"{message.author.mention}, you're sending messages too quickly in this AI channel! Please wait a moment.")
            return # Do not process this set channel trigger

        # Process with Gemini for set channel (main chat history)
        main_chat_history = bot_data[server_id]["main_chat_history"]

        # Construct prompt for Gemini (adjust format for actual Gemini API)
        gemini_history = main_chat_history # Assuming main_chat_history is already in Gemini format

        # Use DEFAULT_SYSTEM_PROMPT for set channel interactions.
        # No specific override needed here unless a different persona is desired for set_channels.
        # get_gemini_response will use DEFAULT_SYSTEM_PROMPT if system_prompt_override is None.
        
        try:
            response_text = await get_gemini_response(gemini_history, message.content) # No override, uses DEFAULT_SYSTEM_PROMPT
            await message.channel.send(response_text)

            # Update main chat history (FIFO)
            main_chat_history.append({"role": "user", "parts": [message.content]})
            main_chat_history.append({"role": "model", "parts": [response_text]})
            if len(main_chat_history) > 200: # Keep last 200 entries for main chat
                main_chat_history.pop(0)
                main_chat_history.pop(0)

            save_data(bot_data)
            logging.info(f"Set channel response sent in channel {channel_id}.")
        except Exception as e:
            logging.error(f"Error during set-channel Gemini interaction: {e}")
            await message.channel.send("Sorry, I couldn't continue our conversation right now.")

# --- Bot Commands ---
@bot.command(name="setchannel", help=f"Sets the current channel for continuous conversation. Use: {COMMAND_PREFIX}setchannel")
async def set_channel_cmd(ctx):
    """Sets the current channel as a 'set channel' for continuous AI interaction."""
    server_id = str(ctx.guild.id)
    channel_id = ctx.channel.id

    ensure_server_data(server_id)

    if channel_id not in bot_data[server_id]["set_channels"]:
        bot_data[server_id]["set_channels"].append(channel_id)
        save_data(bot_data)
        await ctx.send(f"This channel ({ctx.channel.mention}) has been set for continuous conversation.")
        logging.info(f"Channel {channel_id} set for continuous conversation in server {server_id}.")
    else:
        await ctx.send(f"This channel ({ctx.channel.mention}) is already set for continuous conversation.")

@bot.command(name="unsetchannel", help=f"Unsets the current channel from continuous conversation. Use: {COMMAND_PREFIX}unsetchannel")
async def unset_channel_cmd(ctx):
    """Unsets the current channel from being a 'set channel'."""
    server_id = str(ctx.guild.id)
    channel_id = ctx.channel.id

    ensure_server_data(server_id)

    if channel_id in bot_data[server_id]["set_channels"]:
        bot_data[server_id]["set_channels"].remove(channel_id)
        save_data(bot_data)
        await ctx.send(f"This channel ({ctx.channel.mention}) has been unset from continuous conversation.")
        logging.info(f"Channel {channel_id} unset from continuous conversation in server {server_id}.")
    else:
        await ctx.send(f"This channel ({ctx.channel.mention}) was not set for continuous conversation.")

@bot.command(name="ignore", help=f"Disables keyword-triggered replies in this channel. Use: {COMMAND_PREFIX}ignore")
async def ignore_cmd(ctx):
    """Disables keyword-triggered replies in the current channel."""
    server_id = str(ctx.guild.id)
    channel_id = ctx.channel.id

    ensure_server_data(server_id)

    if channel_id not in bot_data[server_id]["ignored_channels_for_keywords"]:
        bot_data[server_id]["ignored_channels_for_keywords"].append(channel_id)
        save_data(bot_data)
        await ctx.send(f"Keyword replies are now ignored in this channel ({ctx.channel.mention}).")
        logging.info(f"Channel {channel_id} set to ignore keyword replies in server {server_id}.")
    else:
        await ctx.send(f"Keyword replies are already ignored in this channel ({ctx.channel.mention}).")

@bot.command(name="unignore", help=f"Enables keyword-triggered replies in this channel. Use: {COMMAND_PREFIX}unignore")
async def unignore_cmd(ctx):
    """Enables keyword-triggered replies in the current channel."""
    server_id = str(ctx.guild.id)
    channel_id = ctx.channel.id

    ensure_server_data(server_id)

    if channel_id in bot_data[server_id]["ignored_channels_for_keywords"]:
        bot_data[server_id]["ignored_channels_for_keywords"].remove(channel_id)
        save_data(bot_data)
        await ctx.send(f"Keyword replies are now enabled in this channel ({ctx.channel.mention}).")
        logging.info(f"Channel {channel_id} set to enable keyword replies in server {server_id}.")
    else:
        await ctx.send(f"Keyword replies were not ignored in this channel ({ctx.channel.mention}).")

@bot.command(name="time", help=f"Shows the system uptime. Use: {COMMAND_PREFIX}time")
async def time_cmd(ctx):
    """Shows the system uptime using the 'uptime' command."""
    try:
        result = subprocess.run(['uptime', '-p'], capture_output=True, text=True, check=True)
        uptime_info = result.stdout.strip()
        await ctx.send(f"System uptime: {uptime_info}")
        logging.info(f"Uptime command executed for {ctx.author.name}.")
    except FileNotFoundError:
        await ctx.send("Error: `uptime` command not found on the system.")
        logging.error("`uptime` command not found on the system.")
    except subprocess.CalledProcessError as e:
        await ctx.send(f"Error executing uptime command: {e.stderr.strip()}")
        logging.error(f"Error executing uptime command: {e.stderr.strip()}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")
        logging.error(f"An unexpected error occurred during uptime command: {e}")

@bot.command(name="help", help=f"Shows this help message. Use: {COMMAND_PREFIX}help")
async def help_cmd(ctx):
    """Lists available commands and their basic usage."""
    help_message = f"""
**Available commands (prefix: `{COMMAND_PREFIX}`):**
- `{COMMAND_PREFIX}help`: Shows this message.
- `{COMMAND_PREFIX}setchannel`: Sets the current channel for continuous conversation.
- `{COMMAND_PREFIX}unsetchannel`: Unsets the current channel from continuous conversation.
- `{COMMAND_PREFIX}ignore`: Disables keyword-triggered replies in this channel.
- `{COMMAND_PREFIX}unignore`: Enables keyword-triggered replies in this channel.
- `{COMMAND_PREFIX}time`: Shows the system uptime.

*Note: If a channel is set for continuous conversation, I will respond to every message.
If not, I will only respond if you mention a keyword (like 'ai', 'bot', 'assistant', or my name)
and the channel is not ignored for keywords.*
"""
    await ctx.send(help_message)
    logging.info(f"Help message sent to {ctx.author.name} in channel {ctx.channel.id}.")

# --- Run the bot ---
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logging.critical("DISCORD_TOKEN not found in .env. Please set it to run the bot.")
        print("Error: DISCORD_TOKEN not found in .env. Please set it to run the bot.")
    else:
        try:
            bot.run(DISCORD_TOKEN)
        except discord.LoginFailure:
            logging.critical("Invalid Discord token. Please check your DISCORD_TOKEN in .env.")
            print("Error: Invalid Discord token. Please check your DISCORD_TOKEN in .env.")
        except Exception as e:
            logging.critical(f"An unexpected error occurred while running the bot: {e}")
            print(f"An unexpected error occurred while running the bot: {e}")
