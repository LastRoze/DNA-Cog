from redbot.core import commands
import os
import platform

class RestartPC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def restartpc(self, ctx):
        """Restarts the server's PC. Only the server owner can use this command."""
        if ctx.guild.owner == ctx.author:
            await ctx.send("Restarting the PC...")
            self.restart_computer()
        else:
            await ctx.send("You are not the server owner and cannot use this command.")

    def restart_computer(self):
        """Restarts the computer based on the operating system."""
        if platform.system() == "Windows":
            os.system("shutdown /r /t 0")
        elif platform.system() == "Linux":
            os.system("sudo reboot")
        else:
            raise OSError("Unsupported operating system for restart command.")
