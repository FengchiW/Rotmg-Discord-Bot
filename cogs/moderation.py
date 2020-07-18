import datetime
import json
import logging

import aiohttp
import discord
from discord.ext import commands

import checks
import embeds
import sql
import utils
from checks import manual_verify_channel, has_manage_roles
from cogs import verification
from sql import get_guild, get_user, update_user, add_new_user, gld_cols, usr_cols

logger = logging.getLogger('discord')


class Moderation(commands.Cog):
    """Commands for user/server management"""
    def __init__(self, client):
        self.client = client

    @commands.command(usage="change_prefix <prefix>", description="Change the bot's prefix for all commands.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def change_prefix(self, ctx, prefix):
        with open('data/prefixes.json', 'r') as file:
            prefixes = json.load(file)

        prefixes[str(ctx.guild.id)] = prefix

        with open('data/prefixes.json', 'w') as file:
            json.dump(prefixes, file, indent=4)

        await ctx.send(f"The prefix for this server has been changed to '{prefix}'.")

    @commands.command(usage="find <nickname>", description="Find a user by the specified nickname.")
    @commands.guild_only()
    @checks.is_rl_or_higher_check()
    async def find(self, ctx, member: utils.MemberLookupConverter):
        if member.voice is None:
            vc = '❌'
        else:
            vc = f"`{member.voice.channel.name}`"

        if member.nick and " | " in member.nick: # Check if user has an alt account
            names = member.nick.split(" | ")
            desc = f"Found {member.mention} with the ign's: "
            desc += " | ".join(['['+''.join([n for n in name if n.isalpha()])+'](https://www.realmeye.com/player/'+''.join([n for n in name if n.isalpha()])+")" for name in names])
            desc += f"\nVoice Channel: {vc}"
        else:
            name = ''.join([i for i in member.display_name if i.isalpha()])
            desc = f"Found {member.mention} with the ign: [{name}](https://www.realmeye.com/player/{name})\nVoice Channel: {vc}"

        embed = discord.Embed(description=desc, color=discord.Color.green())

        data = await sql.get_users_punishments(self.client.pool, member.id, ctx.guild.id)
        if data:
            pages = []
            embed.add_field(name="Punishments:", value=f"Found `{len(data)}` punishments in this user's history.\nUse the reactions below "
                                                       "to navigate through them.")
            pages.append(embed)
            for i, r in enumerate(data):
                requester = await ctx.guild.fetch_member(r[sql.punish_cols.r_uid])
                active = "✅" if r[sql.punish_cols.active] else "❌"
                starttime = f"Issued at: `{r[sql.punish_cols.starttime].strftime('%b %d %Y %H:%M:%S')}`"
                endtime = f"\nEnded at: `{r[sql.punish_cols.endtime].strftime('%b %d %Y %H:%M:%S')}`" if r[sql.punish_cols.endtime] else ""
                ptype = r[sql.punish_cols.type].capitalize()
                color = discord.Color.orange() if ptype == "Warn" else discord.Color.red() if ptype == "Suspend" else \
                    discord.Color.from_rgb(0, 0, 0)
                pembed = discord.Embed(title=f"Punishment Log #{i+1} - {ptype}", color=color)
                pembed.description = f"Punished member: {member.mention}\n**{ptype}** issued by {requester.mention}\nActive: {active}"
                pembed.add_field(name="Reason:", value=r[sql.punish_cols.reason])
                pembed.add_field(name="Time:", value=starttime+endtime)
                pages.append(pembed)
            paginator = utils.EmbedPaginator(self.client, ctx, pages)
            await paginator.paginate()
        else:
            embed.add_field(name="Punishments:", value="No punishment logs found!")
            await ctx.send(embed=embed)


    @commands.command(usage='addalt <member> <altname>', description="Add an alternate account to a user (limit 2).")
    @commands.guild_only()
    @checks.is_security_or_higher_check()
    async def addalt(self, ctx, member: utils.MemberLookupConverter, altname):
        async with aiohttp.ClientSession() as cs:
            async with cs.get(f'https://rotmg-discord-bot.wm.r.appspot.com/?player={altname}', ssl=False) as r:
                if r.status == 403:
                    print("ERROR: API ACCESS FORBIDDEN")
                    await ctx.send(f"<@{self.client.owner_id}> ERROR: API ACCESS REVOKED!.")
                data = await r.json()  # returns dict
        if not data:
            return await ctx.send("There was an issue retrieving realmeye data. Please try the command later.")
        if 'error' in data:
            embed = discord.Embed(title='Error!', description=f"There were no players found on realmeye with the name `{altname}`.",
                                  color=discord.Color.red())
            return await ctx.send(embed=embed)

        cleaned_name = str(data["player"])
        res = await sql.add_alt_name(self.client.pool, member.id, cleaned_name)
        if not res:
            embed = discord.Embed(title="Error!", description="The user specified already has 2 alts added!", color=discord.Color.red())
            return await ctx.send(embed=embed)

        name = member.display_name

        if cleaned_name.lower() in name.lower():
            if res:
                embed = discord.Embed(title="Success!", description=f"The alt with the name `{cleaned_name}` was already added to "
                                                                    f"{member.mention}'s name, but was added to the database.")
            else:
                embed = discord.Embed(title="Error!", description="The user specified already has this alt linked to their name!",
                                  color=discord.Color.red())
            return await ctx.send(embed=embed)

        name += f" | {cleaned_name}"
        try:
            await member.edit(nick=name)
        except discord.Forbidden:
            return await ctx.send("There was an error adding the alt to this person's name (Perms).\n"
                           f"Please copy this and add it to their name manually: ` | {cleaned_name}`\n{member.mention}")

        embed = discord.Embed(title="Success!", description=f"`{cleaned_name}` was added as an alt to {member.mention}.",
                              color=discord.Color.green())
        await ctx.send(embed=embed)


    @commands.command(usage='removealt <member> <altname>', description="Remove an alt from a player.")
    @commands.guild_only()
    @checks.is_security_or_higher_check()
    async def removealt(self, ctx, member: utils.MemberLookupConverter, altname):
        res = await sql.remove_alt_name(self.client.pool, member.id, altname)

        if not res:
            embed = discord.Embed(title="Error!", description=f"The user specified doesn't have an alt in the database called `{altname}`!",
                                  color=discord.Color.red())
            await ctx.send(embed=embed)

        clean_names = []
        if altname.lower() in member.display_name.lower():
            names = member.display_name.split(" | ")
            for n in names:
                if n.lower() != altname.lower():
                    clean_names.append(n)
        nname = " | ".join(clean_names)

        try:
            await member.edit(nick=nname)
        except discord.Forbidden:
            return await ctx.send("There was an error adding the alt to this person's name (Perms).\n"
                                  f"Please copy this and replace their nickname manually: ` | {nname}`\n{member.mention}")

        embed = discord.Embed(title="Success!", description=f"`{altname}` was removed as an alt to {member.mention}.",
                              color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command(usage="purge <num> [ignore_pinned]",
                      description="Removes [num] messages from the channel, ignore_pinned = 0 to ignore, 1 to delete pinned")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, num=5, ignore_pinned=0):
        num += 1
        if not isinstance(num, int):
            await ctx.send("Please pass in a number of messages to delete.")
            return

        no_older_than = datetime.datetime.utcnow()-datetime.timedelta(days=14)+datetime.timedelta(seconds=1)
        if ignore_pinned == 0:
            n = len(await ctx.channel.purge(limit=num, check=is_not_pinned, after=no_older_than, bulk=True))
        else:
            n = len(await ctx.channel.purge(limit=num, after=no_older_than, bulk=True))
        if n < num:
            return await ctx.send("You are trying to delete messages that are older than 15 days. Discord API doesn't "
                                  "allow bots to do this!\nYou can use the nuke command to completely clean a "
                                  "channel.", delete_after=10)
        await ctx.send(f"Deleted {n-1} messages.", delete_after=5)

    @commands.command(usage='nuke', description="Deletes all the messages in a channel.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx, confirmation=""):
        if confirmation == "I confirm this action.":
            newc = await ctx.channel.clone()
            await newc.edit(position=ctx.channel.position)
            await ctx.channel.delete()
        else:
            return await ctx.send('Please confirm you would like to do this by running: `!nuke "I confirm this '
                                  'action."`\n**__THIS WILL DELETE ALL MESSAGES IN THE CHANNEL!__**')

    @commands.command(usage="manual_verify <member> <ign>",
                      description="Manually verify someone - INCLUDE THEIR IGN HOW IT'S SPELLED IN-GAME (Including Capitalization).")
    @commands.guild_only()
    @commands.check_any(manual_verify_channel(), has_manage_roles())
    async def manual_verify(self, ctx, member: utils.MemberLookupConverter, ign):
        await ctx.message.delete()
        return await manual_verify_ext(self.client.pool, ctx.guild, member.id, ctx.author, ign)

    @commands.command(usage="manual_verify_deny <member>", description="Deny someone from manual_verification.")
    @commands.guild_only()
    @commands.check_any(manual_verify_channel(), has_manage_roles())
    async def manual_verify_deny(self, ctx, member: utils.MemberLookupConverter):
        await ctx.message.delete()
        return await manual_verify_deny_ext(self.client.pool, ctx.guild, member.id, ctx.author)


def setup(client):
    client.add_cog(Moderation(client))

async def manual_verify_ext(pool, guild, uid, requester, ign=None):
    """Manually verifies user with specified uid"""
    guild_data = await get_guild(pool, guild.id)
    channel = guild.get_channel(guild_data[gld_cols.manualverifychannel])
    member = guild.get_member(int(uid))
    user_data = await get_user(pool, int(uid))

    if user_data is not None: # check if user exists in DB
        name = user_data[usr_cols.ign]
        status = user_data[usr_cols.status]
        if status != 'verified':
            if status != "stp_1" and status != "stp_2":
                if status == 'deny_appeal':
                    channel = guild.get_channel(guild_data[gld_cols.manualverifychannel])
                    try:
                        message = await channel.fetch_message(user_data[usr_cols.verifyid])
                        await message.delete()
                    except discord.NotFound:
                        pass
                if ign is not None:
                    name = ign
            elif ign is not None:
                name = ign
            else:
                await channel.send("Please specify an IGN for this user.")
                return
        else:
            await channel.send("The specified member has already been verified.")
    elif ign is not None:
        await add_new_user(pool, int(uid), guild.id, None)
        user_data = await get_user(pool, int(uid))
        name = ign
    else:
        return await channel.send("Please specify an IGN for this user.")

    await verification.complete_verification(pool, guild, guild_data, member, name, user_data, False)
    embed = discord.Embed(
        description=f"✅ {member.mention} ***has been manually verified by*** {requester.mention}***.***",
        color=discord.Color.green())
    await channel.send(embed=embed)

async def manual_verify_deny_ext(pool, guild, uid, requester):
    """Manually verifies user with specified uid"""
    guild_data = await get_guild(pool, guild.id)
    channel = guild.get_channel(guild_data[gld_cols.manualverifychannel])
    member = guild.get_member(int(uid))
    user_data = await get_user(pool, int(uid))

    if user_data is not None:
        status = user_data[usr_cols.status]
        if status != 'verified':
            if status == 'deny_appeal':
                channel = guild.get_channel(guild_data[gld_cols.manualverifychannel])
                message = await channel.fetch_message(user_data[usr_cols.verifyid])
                await message.delete()
        else:
            await channel.send("The specified member has already been verified.")

    await update_user(pool, member.id, "status", "appeal_denied")
    guilds = user_data[usr_cols.verifiedguilds]
    if guilds is None:
        guilds = []
    else:
        guilds = guilds.split(",")
    guilds.append(guild.name)
    # await update_user(pool, member.id, "verifiedguilds", ','.join(guilds))
    await update_user(pool, member.id, "verifyguild", None)
    await update_user(pool, member.id, "verifykey", None)
    await update_user(pool, member.id, "verifyid", None)
    embed = embeds.verification_denied(member.mention, requester.mention)
    await member.send(embed=embed)

    embed = discord.Embed(
        description=f"❌ {member.mention} ***has been denied verification by*** {requester.mention}***.***",
        color=discord.Color.red())
    await channel.send(embed=embed)


def is_not_pinned(msg):
    return False if msg.pinned else True