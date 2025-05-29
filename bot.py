import os
import json
import discord
from discord.ext import commands
from dotenv import load_dotenv
import subprocess
import time
import logging
import google.generativeai as genai
import glob # Import glob for file listing

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
CONTEXT_DIR = os.getenv("CONTEXT_DIR", "context") # New: Directory for context files

# New environment variables for Rate Limiting
RATE_LIMIT_MAX_PROMPTS = int(os.getenv("RATE_LIMIT_MAX_PROMPTS", 3)) # Default to 3 prompts
RATE_LIMIT_SECONDS = int(os.getenv("RATE_LIMIT_SECONDS", 8))     # Default to 8 seconds

# Parse BOT_KEYWORDS_STR into a list. This will be finalized in on_ready.
KEYWORDS = [keyword.strip().lower() for keyword in BOT_KEYWORDS_STR.split(',')]

# Initialize Discord Bot with intents
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
loaded_contexts = {} # New: Stores loaded system prompts from context files

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
    """Ensures the server's data structure exists in bot_data and has all necessary keys."""
    modified = False
    if server_id_str not in bot_data:
        bot_data[server_id_str] = {
            "set_channels": [],
            "main_chat_history": [],
            "ignored_channels_for_keywords": [],
            "user_specific_context": {},
            "channel_active_contexts": {}
        }
        logging.info(f"Initialized new data structure for server: {server_id_str}")
        modified = True
    else:
        # Check and add missing keys for existing server entries
        server_entry = bot_data[server_id_str]
        keys_added = []
        if "set_channels" not in server_entry:
            server_entry["set_channels"] = []
            keys_added.append("set_channels")
        if "main_chat_history" not in server_entry:
            server_entry["main_chat_history"] = []
            keys_added.append("main_chat_history")
        if "ignored_channels_for_keywords" not in server_entry:
            server_entry["ignored_channels_for_keywords"] = []
            keys_added.append("ignored_channels_for_keywords")
        if "user_specific_context" not in server_entry:
            server_entry["user_specific_context"] = {}
            keys_added.append("user_specific_context")
        if "channel_active_contexts" not in server_entry: # This is the key causing the error
            server_entry["channel_active_contexts"] = {}
            keys_added.append("channel_active_contexts")
        
        if keys_added:
            logging.info(f"Added missing key(s) {', '.join(keys_added)} to server: {server_id_str}")
            modified = True
            
    if modified:
        save_data(bot_data)

def ensure_user_data(server_id_str, user_id_str):
    """Ensures the user's data structure exists and has all necessary keys."""
    ensure_server_data(server_id_str) # This will ensure bot_data[server_id_str]["user_specific_context"] exists

    user_contexts = bot_data[server_id_str]["user_specific_context"]
    modified = False

    if user_id_str not in user_contexts:
        user_contexts[user_id_str] = {
            "rolling_history": [],
            "profile_summary": ""
        }
        logging.info(f"Initialized new user context for user: {user_id_str} in server: {server_id_str}")
        modified = True
    else:
        user_entry = user_contexts[user_id_str]
        keys_added = []
        if "rolling_history" not in user_entry:
            user_entry["rolling_history"] = []
            keys_added.append("rolling_history")
        if "profile_summary" not in user_entry:
            user_entry["profile_summary"] = ""
            keys_added.append("profile_summary")
        
        if keys_added:
            logging.info(f"Added missing key(s) {', '.join(keys_added)} for user: {user_id_str} in server: {server_id_str}")
            modified = True
            
    if modified:
        save_data(bot_data)

# --- Context Loading Function ---
def load_contexts():
    """Loads system prompts from text files in the CONTEXT_DIR."""
    global loaded_contexts
    loaded_contexts = {} # Clear existing contexts
    if not os.path.exists(CONTEXT_DIR):
        logging.warning(f"Context directory '{CONTEXT_DIR}' not found. No custom contexts will be loaded.")
        return

    for filepath in glob.glob(os.path.join(CONTEXT_DIR, "*.txt")):
        filename = os.path.basename(filepath)
        context_name = os.path.splitext(filename)[0].lower() # Use filename without extension as context name
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
                loaded_contexts[context_name] = content
                logging.info(f"Loaded context: '{context_name}' from '{filename}'")
        except Exception as e:
            logging.error(f"Error loading context file '{filename}': {e}")
    
    if not loaded_contexts:
        logging.info(f"No context files found in '{CONTEXT_DIR}'.")
    else:
        logging.info(f"Available contexts: {', '.join(loaded_contexts.keys())}")


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

# --- Gemini API Interaction ---
async def get_gemini_response(prompt_history, current_message_content, system_prompt_base, profile_summary_text=""):
    """
    Interacts with the Gemini API.
    Combines system_prompt_base and profile_summary_text for the AI's context.
    """
    if not model: # Check if the global 'model' object was successfully initialized
        logging.warning("Gemini model not available. Returning placeholder.")
        return "My AI capabilities are currently disabled (model not loaded)."

    # Construct the final system prompt
    final_system_prompt = system_prompt_base
    if profile_summary_text:
        final_system_prompt += f"\n\nUser profile context: {profile_summary_text}"
    
    logging.debug(f"Final system context for Gemini: '{final_system_prompt}'") # Changed to debug
    logging.debug(f"Sending to Gemini - History: {prompt_history}, Current: {current_message_content}")

    try:
        # For Gemini, the system instruction is often the first turn in the history,
        # or set during model initialization for some models.
        # For `start_chat`, we prepend it to the history if it's not already there.
        # Gemini's `start_chat` expects history to be a list of `{"role": "user/model", "parts": [{"text": "..."}]}`
        
        # Create a temporary history including the system prompt as the first user turn
        # This is a common way to pass system instructions to chat models if not directly supported
        # by a dedicated parameter.
        temp_history = []
        if final_system_prompt:
            temp_history.append({"role": "user", "parts": [{"text": final_system_prompt}]})
            temp_history.append({"role": "model", "parts": [{"text": "Okay, I understand."}]}) # Bot acknowledges system prompt
        
        # Append the actual conversation history
        temp_history.extend(prompt_history)

        chat_session = model.start_chat(history=temp_history)
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
        return "Oops! I encountered an error trying to process that with my AI. Please try again later."

# --- Bot Events ---
@bot.event
async def on_ready():
    """Logs when the bot is ready and connected to Discord."""
    global KEYWORDS # Declare KEYWORDS as global to modify it
    if bot.user and bot.user.name.lower() not in KEYWORDS:
        KEYWORDS.append(bot.user.name.lower())
    
    load_contexts() # New: Load contexts on startup

    logging.info(f'{bot.user} has connected to Discord!')
    logging.info(f'Command Prefix: {COMMAND_PREFIX}')
    logging.info(f'Keywords: {KEYWORDS}') # Log the finalized keywords
    logging.info(f'Gemini Model: {GEMINI_MODEL_NAME if model else "Not loaded/configured"}')
    logging.info(f'Default System Prompt: "{DEFAULT_SYSTEM_PROMPT}"')
    logging.info(f'AI Rate Limit: {RATE_LIMIT_MAX_PROMPTS} prompts per {RATE_LIMIT_SECONDS} seconds per user.')
    logging.info(f'Context Directory: {CONTEXT_DIR}')
    # Fix: Changed outer f-string quotes to double quotes to allow single quotes inside
    logging.info(f"Available Contexts: {', '.join(loaded_contexts.keys()) if loaded_contexts else 'None'}")
    
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
    channel_id = str(message.channel.id) # Convert to string for dictionary keys
    user_id = str(message.author.id)
    message_content = message.content.lower()

    # Ensure server and user data structures exist
    ensure_server_data(server_id)
    ensure_user_data(server_id, user_id)

    # --- Command Processing ---
    # Let the commands.Bot handle commands first.
    if message.content.startswith(COMMAND_PREFIX):
        await bot.process_commands(message)
        return # Command handled, stop further processing

    # --- Determine the base system prompt for this interaction ---
    # Check if a specific context is set for this channel
    channel_context_name = bot_data[server_id]["channel_active_contexts"].get(channel_id)
    system_prompt_base_for_gemini = loaded_contexts.get(channel_context_name, DEFAULT_SYSTEM_PROMPT)

    # --- Keyword Detection Logic ---
    ignored_channels = bot_data[server_id]["ignored_channels_for_keywords"]

    is_keyword_triggered = any(keyword in message_content for keyword in KEYWORDS)

    if is_keyword_triggered and int(channel_id) not in ignored_channels: # Convert channel_id back to int for 'ignored_channels' list
        # Apply Rate Limiting for Keyword Triggers
        if not check_and_update_rate_limit(user_id, server_id):
            await message.channel.send(f"{message.author.mention}, you're asking for AI responses a bit too quickly! Please wait a moment.")
            return # Do not process this keyword trigger

        # Process with Gemini for keyword trigger (user-specific context)
        user_context = bot_data[server_id]["user_specific_context"][user_id]
        rolling_history = user_context["rolling_history"]
        profile_summary = user_context["profile_summary"]

        # Construct prompt for Gemini
        gemini_history = rolling_history # Assuming rolling_history is already in Gemini format
        
        try:
            response_text = await get_gemini_response(gemini_history, message.content, system_prompt_base_for_gemini, profile_summary)
            await message.channel.send(response_text)

            # Update rolling history (FIFO)
            rolling_history.append({"role": "user", "parts": [{"text": message.content}]})
            rolling_history.append({"role": "model", "parts": [{"text": response_text}]})
            if len(rolling_history) > 100: # Keep last 100 entries (50 user/bot pairs)
                rolling_history.pop(0)
                rolling_history.pop(0)

            save_data(bot_data)
            logging.info(f"Keyword triggered response sent in channel {channel_id} for user {user_id}.")
        except Exception as e:
            logging.error(f"Error during keyword-triggered Gemini interaction: {e}")
            await message.channel.send("Sorry, I couldn't process that keyword request right now.")
        return # Keyword interaction handled, stop further processing

    # --- Set Channel Interaction Logic ---
    set_channels = bot_data[server_id]["set_channels"]
    if int(channel_id) in set_channels: # Convert channel_id back to int for 'set_channels' list
        # Apply Rate Limiting for Set Channel Triggers
        if not check_and_update_rate_limit(user_id, server_id):
            await message.channel.send(f"{message.author.mention}, you're sending messages too quickly in this AI channel! Please wait a moment.")
            return # Do not process this set channel trigger

        # Process with Gemini for set channel (main chat history)
        main_chat_history = bot_data[server_id]["main_chat_history"]

        # Construct prompt for Gemini
        gemini_history = main_chat_history # Assuming main_chat_history is already in Gemini format
        
        try:
            response_text = await get_gemini_response(gemini_history, message.content, system_prompt_base_for_gemini, "") # No profile summary for set channels
            await message.channel.send(response_text)

            # Update main chat history (FIFO)
            main_chat_history.append({"role": "user", "parts": [{"text": message.content}]})
            main_chat_history.append({"role": "model", "parts": [{"text": response_text}]})
            if len(main_chat_history) > 200: # Keep last 200 entries (100 user/bot pairs)
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

@bot.command(name="setcontext", help=f"Sets a specific AI context for this channel. Use: {COMMAND_PREFIX}setcontext <context_name>")
async def set_context_cmd(ctx, context_name: str):
    """Sets a specific AI context (system prompt) for the current channel."""
    server_id = str(ctx.guild.id)
    channel_id = str(ctx.channel.id)
    context_name_lower = context_name.lower()

    ensure_server_data(server_id)

    if context_name_lower in loaded_contexts:
        bot_data[server_id]["channel_active_contexts"][channel_id] = context_name_lower
        save_data(bot_data)
        await ctx.send(f"AI context for this channel ({ctx.channel.mention}) set to: `{context_name_lower}`.")
        logging.info(f"Channel {channel_id} context set to '{context_name_lower}' in server {server_id}.")
    else:
        available_contexts = ", ".join(loaded_contexts.keys()) if loaded_contexts else "None"
        await ctx.send(f"Context `{context_name}` not found. Available contexts: {available_contexts}")
        logging.warning(f"Attempted to set unknown context '{context_name}' for channel {channel_id}.")

@bot.command(name="unsetcontext", help=f"Removes the custom AI context for this channel. Use: {COMMAND_PREFIX}unsetcontext")
async def unset_context_cmd(ctx):
    """Removes the custom AI context for the current channel, reverting to default."""
    server_id = str(ctx.guild.id)
    channel_id = str(ctx.channel.id)

    ensure_server_data(server_id)

    if channel_id in bot_data[server_id]["channel_active_contexts"]:
        del bot_data[server_id]["channel_active_contexts"][channel_id]
        save_data(bot_data)
        await ctx.send(f"Custom AI context for this channel ({ctx.channel.mention}) has been removed. Reverting to default.")
        logging.info(f"Channel {channel_id} context unset in server {server_id}.")
    else:
        await ctx.send(f"This channel ({ctx.channel.mention}) does not have a custom AI context set.")

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
- `{COMMAND_PREFIX}setcontext <context_name>`: Sets a specific AI context (persona/topic) for this channel. Contexts are loaded from the `{CONTEXT_DIR}` directory.
- `{COMMAND_PREFIX}unsetcontext`: Removes the custom AI context for this channel, reverting to the default.
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
