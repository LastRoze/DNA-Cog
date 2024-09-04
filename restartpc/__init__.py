from .restartpc import RestartPC

async def setup(bot):
    cog = RestartPC(bot)
    await bot.add_cog(cog)
