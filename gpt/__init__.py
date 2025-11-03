from .gpt import GPT

async def setup(bot):
    await bot.add_cog(GPT(bot))