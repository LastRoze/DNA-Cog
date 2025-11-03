import discord
from redbot.core import commands, Config
import aiohttp
import asyncio
from typing import Optional
import traceback
from datetime import datetime

class GPT(commands.Cog):
    """Interact with ChatGPT using GPT-4o-mini model"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_global = {
            "api_key": "",              # set with [p]gptset apikey
            "model": "gpt-4o-mini",
            "max_tokens": 1000,         # matches your setter constraints
            "temperature": 0.7,
            "log_channel_id": 0,        # set with [p]gptset log
            "allowed_channel_ids": []   # empty => allowed everywhere
        }
        self.config.register_global(**default_global)
        self.session: Optional[aiohttp.ClientSession] = None
        
    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def log_error(self, error_type: str, error_message: str, ctx: Optional[commands.Context] = None):
        """Log errors to the designated log channel"""
        try:
            log_channel_id = await self.config.log_channel_id()
            if not log_channel_id:
                return
            
            log_channel = self.bot.get_channel(log_channel_id)
            if not log_channel:
                return
            
            embed = discord.Embed(
                title=f"🚨 GPT Error: {error_type}",
                description=f"```{error_message[:1900]}```",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            
            if ctx:
                embed.add_field(name="User", value=f"{ctx.author} ({ctx.author.id})", inline=True)
                embed.add_field(name="Channel", value=f"{ctx.channel.mention} ({ctx.channel.id})", inline=True)
                if ctx.guild:
                    embed.add_field(name="Guild", value=f"{ctx.guild.name} ({ctx.guild.id})", inline=True)
                if hasattr(ctx, 'message') and ctx.message.content:
                    query = ctx.message.content[:100]
                    embed.add_field(name="Query", value=query, inline=False)
            
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"Failed to log error: {e}")
    
    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def gpt(self, ctx: commands.Context, *, query: str):
        """
        Ask ChatGPT a question
        
        Usage: [p]gpt <your question>
        Example: [p]gpt What is the meaning of life?
        """
        # Check if channel is allowed
        allowed_channels = await self.config.allowed_channel_ids()
        if allowed_channels and ctx.channel.id not in allowed_channels:
            await ctx.send("❌ This command can only be used in designated channels.")
            return
        
        if not query:
            await ctx.send("❌ Please provide a question! Usage: `[p]gpt <your question>`")
            return
        
        async with ctx.typing():
            try:
                # Get configuration
                api_key = await self.config.api_key()
                model = await self.config.model()
                max_tokens = await self.config.max_tokens()
                temperature = await self.config.temperature()
                
                # Prepare API request
                session = await self.get_session()
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "user", "content": query}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                
                # Make API request
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        await self.log_error(
                            f"API Error ({response.status})",
                            f"Status: {response.status}\nResponse: {error_text}",
                            ctx
                        )
                        
                        if response.status == 401:
                            await ctx.send("❌ Invalid API key. Please contact the bot owner.")
                        elif response.status == 429:
                            await ctx.send("❌ Rate limit exceeded. Please try again later.")
                        elif response.status == 400:
                            await ctx.send("❌ Bad request. Your query may be too long or invalid.")
                        else:
                            await ctx.send(f"❌ API Error ({response.status}). The error has been logged.")
                        return
                    
                    data = await response.json()
                    
                    # Extract response
                    if "choices" in data and len(data["choices"]) > 0:
                        answer = data["choices"][0]["message"]["content"]
                        
                        # Format response in markdown code blocks
                        # Discord limit is 2000 chars, markdown wrapper is 13 chars (```markdown\n + \n```)
                        # So we need to chunk at 1850 to be safe with embed overhead
                        
                        if len(answer) > 1850:
                            # Split into chunks
                            chunks = []
                            current_chunk = ""
                            
                            for line in answer.split('\n'):
                                if len(current_chunk) + len(line) + 1 > 1850:
                                    chunks.append(current_chunk)
                                    current_chunk = line + '\n'
                                else:
                                    current_chunk += line + '\n'
                            
                            if current_chunk:
                                chunks.append(current_chunk)
                            
                            # Send chunks
                            for i, chunk in enumerate(chunks):
                                embed = discord.Embed(
                                    title=f"💬 ChatGPT Response (Part {i+1}/{len(chunks)})",
                                    description=f"```markdown\n{chunk.strip()}\n```",
                                    color=discord.Color.green()
                                )
                                if i == 0:
                                    embed.set_footer(text=f"Question by {ctx.author.name}")
                                await ctx.send(embed=embed)
                        else:
                            embed = discord.Embed(
                                title="💬 ChatGPT Response",
                                description=f"```markdown\n{answer}\n```",
                                color=discord.Color.green()
                            )
                            embed.set_footer(text=f"Question by {ctx.author.name}")
                            await ctx.send(embed=embed)
                    else:
                        error_msg = "No choices in API response"
                        await self.log_error("Invalid Response", f"Response data: {str(data)[:500]}", ctx)
                        await ctx.send("❌ No response from ChatGPT. The error has been logged.")
                        
            except asyncio.TimeoutError:
                await self.log_error("Timeout Error", "Request timed out after 30 seconds", ctx)
                await ctx.send("❌ Request timed out. Please try again.")
            except aiohttp.ClientError as e:
                await self.log_error("Connection Error", f"{type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}", ctx)
                await ctx.send(f"❌ Connection error. The error has been logged.")
            except Exception as e:
                await self.log_error("Unexpected Error", f"{type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}", ctx)
                await ctx.send(f"❌ An unexpected error occurred. The error has been logged.")
                raise  # Re-raise for Red's error handler
    
    @commands.group()
    @commands.is_owner()
    async def gptset(self, ctx: commands.Context):
        """Configure GPT settings (Bot Owner Only)"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @gptset.command(name="apikey")
    async def set_apikey(self, ctx: commands.Context, api_key: str):
        """Set the OpenAI API key"""
        await self.config.api_key.set(api_key)
        await ctx.send("✅ API key updated successfully!")
        try:
            await ctx.message.delete()
        except:
            pass
    
    @gptset.command(name="token")
    async def set_token(self, ctx: commands.Context, api_key: str):
        """Set the OpenAI API token (alias for apikey)"""
        await self.config.api_key.set(api_key)
        await ctx.send("✅ API token updated successfully!")
        try:
            await ctx.message.delete()
        except:
            pass
    
    @gptset.command(name="model")
    async def set_model(self, ctx: commands.Context, model: str):
        """
        Set the GPT model to use
        
        Common models: gpt-4o-mini, gpt-4o, gpt-4-turbo, gpt-3.5-turbo
        """
        await self.config.model.set(model)
        await ctx.send(f"✅ Model set to: {model}")
    
    @gptset.command(name="tokens")
    async def set_tokens(self, ctx: commands.Context, max_tokens: int):
        """Set maximum tokens for responses (default: 500)"""
        if max_tokens < 50 or max_tokens > 4000:
            await ctx.send("❌ Max tokens must be between 50 and 4000")
            return
        await self.config.max_tokens.set(max_tokens)
        await ctx.send(f"✅ Max tokens set to: {max_tokens}")
    
    @gptset.command(name="temperature")
    async def set_temperature(self, ctx: commands.Context, temperature: float):
        """Set response temperature (0.0-2.0, default: 0.7)"""
        if temperature < 0 or temperature > 2:
            await ctx.send("❌ Temperature must be between 0.0 and 2.0")
            return
        await self.config.temperature.set(temperature)
        await ctx.send(f"✅ Temperature set to: {temperature}")
    
    @gptset.command(name="log")
    async def set_log_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set the channel for error logging
        
        Usage: [p]gptset log #channel
        or: [p]gptset log 396650046537596928
        """
        await self.config.log_channel_id.set(channel.id)
        await ctx.send(f"✅ Error log channel set to: {channel.mention}")
        
        # Send test log
        embed = discord.Embed(
            title="✅ GPT Error Logging Enabled",
            description="This channel will now receive error logs from the GPT cog.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Set by", value=f"{ctx.author} ({ctx.author.id})")
        await channel.send(embed=embed)
    
    @gptset.command(name="channel")
    async def set_allowed_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Add a channel where users can use the gpt command
        
        Usage: [p]gptset channel #channel
        or: [p]gptset channel 123456789
        """
        allowed_channels = await self.config.allowed_channel_ids()
        
        if channel.id in allowed_channels:
            await ctx.send(f"❌ {channel.mention} is already in the allowed channels list.")
            return
        
        allowed_channels.append(channel.id)
        await self.config.allowed_channel_ids.set(allowed_channels)
        await ctx.send(f"✅ Added {channel.mention} to allowed channels.")
    
    @gptset.command(name="removechannel")
    async def remove_allowed_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Remove a channel from the allowed channels list
        
        Usage: [p]gptset removechannel #channel
        """
        allowed_channels = await self.config.allowed_channel_ids()
        
        if channel.id not in allowed_channels:
            await ctx.send(f"❌ {channel.mention} is not in the allowed channels list.")
            return
        
        allowed_channels.remove(channel.id)
        await self.config.allowed_channel_ids.set(allowed_channels)
        await ctx.send(f"✅ Removed {channel.mention} from allowed channels.")
    
    @gptset.command(name="clearallchannels")
    async def clear_allowed_channels(self, ctx: commands.Context):
        """Clear all allowed channels (allows GPT in all channels)"""
        await self.config.allowed_channel_ids.set([])
        await ctx.send("✅ Cleared all channel restrictions. GPT command can now be used in any channel.")
    
    @gptset.command(name="listchannels")
    async def list_allowed_channels(self, ctx: commands.Context):
        """List all allowed channels"""
        allowed_channels = await self.config.allowed_channel_ids()
        
        if not allowed_channels:
            await ctx.send("ℹ️ No channel restrictions set. GPT command can be used in any channel.")
            return
        
        embed = discord.Embed(
            title="📋 Allowed Channels for GPT Command",
            color=discord.Color.blue()
        )
        
        channel_list = []
        for channel_id in allowed_channels:
            channel = self.bot.get_channel(channel_id)
            if channel:
                channel_list.append(f"• {channel.mention} ({channel_id})")
            else:
                channel_list.append(f"• Unknown Channel ({channel_id})")
        
        embed.description = "\n".join(channel_list) if channel_list else "No valid channels found."
        await ctx.send(embed=embed)
    
    @gptset.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View current GPT settings"""
        api_key = await self.config.api_key()
        model = await self.config.model()
        max_tokens = await self.config.max_tokens()
        temperature = await self.config.temperature()
        log_channel_id = await self.config.log_channel_id()
        allowed_channels = await self.config.allowed_channel_ids()
        
        embed = discord.Embed(
            title="⚙️ GPT Settings",
            color=discord.Color.blue()
        )
        embed.add_field(name="API Key", value=f"{'*' * 20}{api_key[-8:]}", inline=False)
        embed.add_field(name="Model", value=model, inline=True)
        embed.add_field(name="Max Tokens", value=max_tokens, inline=True)
        embed.add_field(name="Temperature", value=temperature, inline=True)
        
        # Log channel
        log_channel = self.bot.get_channel(log_channel_id)
        log_channel_text = log_channel.mention if log_channel else f"ID: {log_channel_id} (Not Found)"
        embed.add_field(name="Log Channel", value=log_channel_text, inline=False)
        
        # Allowed channels
        if allowed_channels:
            channels_text = ", ".join([self.bot.get_channel(cid).mention if self.bot.get_channel(cid) else str(cid) for cid in allowed_channels[:5]])
            if len(allowed_channels) > 5:
                channels_text += f"\n...and {len(allowed_channels) - 5} more"
        else:
            channels_text = "All channels allowed"
        embed.add_field(name="Allowed Channels", value=channels_text, inline=False)
        

        await ctx.send(embed=embed)
