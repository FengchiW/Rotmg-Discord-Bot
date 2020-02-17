import os
import time
import json

import discord
from discord.ext import commands
from discord.utils import get
from dotenv import load_dotenv
import logging

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

load_dotenv()
token = os.getenv('DISCORD_TOKEN')


def get_prefix(client, message):
    if message.guild is None:
        return "!"

    with open('data/prefixes.json', 'r') as file:
        prefixes = json.load(file)

    return prefixes[str(message.guild.id)]


bot = commands.Bot(command_prefix=get_prefix)


@bot.command()
async def load(ctx, extension):
    """Load specified cog"""
    extension = extension.lower()
    bot.load_extension(f'cogs.{extension}')


@bot.command()
async def unload(ctx, extension):
    """Unload specified cog"""
    extension = extension.lower()
    bot.unload_extension(f'cogs.{extension}')


@bot.command()
async def reload(ctx, extension):
    """Reload specified cog"""
    extension = extension.lower()
    bot.unload_extension(f'cogs.{extension}')
    bot.load_extension(f'cogs.{extension}')
    await ctx.send('{} has been reloaded.'.format(extension.capitalize()))


for filename in os.listdir('./cogs/'):
    if filename.endswith('.py'):
        bot.load_extension(f'cogs.{filename[:-3]}')

#Error Handlers
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Please pass in all the required arguments for this command')
    if isinstance(error, commands.CommandNotFound):
        await ctx.send('Invalid command. Use !help to see all of the available commands.')

@bot.event
async def on_error(event, *args, **kwargs):
    with open('err.log', 'a') as f:
        if event == 'on_message':
            f.write(f'Unhandled message: {args[0]}\n')
        else:
            raise

# Checks
with open('data/variables.json', 'r') as file:
    variables = json.load(file)


@bot.check
async def global_perms_check(ctx):
    return True
    # if ctx.message.guild is None:
    #     if ctx.author.id in variables.get('allowed_user_ids'):
    #         return True
    #     return False
    # author_roles = [role.id for role in ctx.author.roles]
    #
    # if len(set(variables.get('allowed_role_ids')).intersection(author_roles)):
    #     return True
    # msg = await ctx.send('{} Does not have the perms to use this command'.format(ctx.author.mention), delete_after=1.5)
    # time.sleep(0.5)
    # await ctx.message.delete()


bot.run(token)