import os
from datetime import datetime
import aiohttp
import discord
import discord_slash
from discord.ext import commands, tasks
from discord_slash import SlashCommand, SlashContext
import mysql.connector
import matplotlib.pyplot as plt
from discord_slash.utils.manage_commands import create_option
from matplotlib.dates import DateFormatter

DBUSER = os.environ['DBUSER']
DBPASSWORD = os.environ['DBPASSWORD']
TOKEN = os.environ['TOKEN']

PREFIX = 'ows!'
bot = commands.Bot(command_prefix=PREFIX, intents=discord.Intents.all())
slash = SlashCommand(bot, sync_commands=True)
guild_ids = [841281357976305684]
updateChannelID = 879819426503999638

# Database
db = mysql.connector.connect(host='192.168.1.61',
                             database='overwatchstats',
                             user=DBUSER,
                             password=DBPASSWORD)


# ====----====----====----====----====----====----====----====----====----====----====----====----
class User:
    def __init__(self, user):
        self.userID = user[0]
        self.discordID = user[1]
        self.battleTag = user[2]


class Game:
    def __init__(self, game):
        self.userID = game[1]
        self.tankRank = game[2]
        self.damageRank = game[3]
        self.supportRank = game[4]
        self.date = game[5]

    def __eq__(self, other):
        if isinstance(other, Game):
            return self.userID == other.userID and self.tankRank == other.tankRank and \
                   self.damageRank == other.damageRank and self.supportRank == other.supportRank
        return False


def getRanks(data):
    tank, damage, support = None, None, None
    ratings = data["ratings"]
    if ratings is None:
        return tank, damage, support

    for rating in range(len(ratings)):
        role = ratings[rating]["role"]
        level = ratings[rating]["level"]
        if role == "tank":
            tank = level
        if role == "damage":
            damage = level
        if role == "support":
            support = level
    return tank, damage, support


async def getProfile(battleTag):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://ow-api.com/v1/stats/pc/eu/" + battleTag + "/complete") as r:
            if r.status == 200:
                return await r.json(), False
            else:
                return None, True


def makeEmbed(name, roleIcon, rankIcon):
    embed = discord.Embed(title=name, colour=discord.Colour(0xfa9c1d), timestamp=datetime.utcnow())
    embed.set_author(name="Full Profile", icon_url=roleIcon)
    embed.set_thumbnail(url=rankIcon)
    embed.set_footer(text="Made by Vic ♥ | ow-api.com")
    return embed


if db.is_connected():
    db_Info = db.get_server_info()
    print("Connected to MySQL Server version ", db_Info)


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    activity = discord.Activity(name=f'data in {len(bot.guilds)} server.', type=discord.ActivityType.watching)
    await bot.change_presence(activity=activity)
    # slash.commands.clear()
    # await discord_slash.manage_commands.remove_all_commands_in(762288517966594059, TOKEN, 680867132300329031)


@bot.event
async def on_slash_command_error(ctx, error):
    if isinstance(error, commands.errors.CommandNotFound):
        await ctx.send("This command does not exist.")
    if isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send("This command seems to be incomplete.")
    if isinstance(error, commands.errors.CommandOnCooldown):
        await ctx.send("This command is on cooldown, please try again later.")
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send("You haven't got enough permissions to run this command.")


@tasks.loop(minutes=5)
async def updateRanks():
    def getPreviousGame(battleTag):
        cursor.execute("select * from games where userID = (select userID from user where battleTag = %s)"
                       " order by gameDate desc; ", (battleTag,))
        return Game(cursor.fetchone())

    async def getCurrentGame(battleTag):
        data, err = await getProfile(battleTag)
        if err or data['private']:
            return None, None, True
        cursor.execute("select * from user where battleTag = %s;", (battleTag,))
        tank, damage, support = getRanks(data)
        return Game([None, cursor.fetchone()[0], tank, damage, support, datetime.now()]), data, None

    def saveGame(game):
        cursor.execute("insert into games (userID,tankRank,damageRank,supportRank,gameDate)"
                       " values (%s, %s, %s, %s, %s)",
                       (game.userID, game.tankRank, game.damageRank, game.supportRank, game.date))
        db.commit()

    def getAllUsers():
        cursor.execute("select * from user;")
        userArray = []
        for row in cursor.fetchall():
            userArray.append(User(row))
        return userArray

    def calculateDiff(previousLevel, newLevel):
        if previousLevel is None:
            diff = "+" + str(newLevel)
        elif newLevel is None:
            diff = 0
        else:
            diff = newLevel - previousLevel
            if diff > 0:
                diff = "+" + str(diff)
        return diff

    def addfield(role, previousLevel, newLevel):
        if not (previousLevel is None and newLevel is None):
            diff = calculateDiff(previousLevel, newLevel)
            embed.add_field(name=role.capitalize() + " previous",
                            value="```" + str(previousLevel) + " SR```", inline=True)
            embed.add_field(name='Difference', value="```diff\n" + str(diff) + "```", inline=True)
            embed.add_field(name=role.capitalize() + " current",
                            value="```" + str(newLevel) + " SR```", inline=True)

    def plotRank(user):
        cursor.execute("select * from games where userID = %s;", (user.userID,))
        games = []
        for game in cursor.fetchall():
            games.append(Game(game))

        x, y1, y2, y3 = [], [], [], []
        for game in games:
            x.append(game.date)
            y1.append(game.tankRank)
            y2.append(game.damageRank)
            y3.append(game.supportRank)
        # plot
        fig, ax = plt.subplots()
        plt.plot(x, y1, label="Tank", marker='o')
        plt.plot(x, y2, label="Damage", marker='o')
        plt.plot(x, y3, label="Support", marker='o')
        plt.title(user.battleTag)
        plt.ylabel("Rank in SR")
        plt.xlabel("Time")
        # beautify the x-labels
        date_form = DateFormatter("%d-%m")
        ax.xaxis.set_major_formatter(date_form)
        plt.gcf().autofmt_xdate()
        plt.legend()
        return plt

    cursor = db.cursor(buffered=True)
    for user in getAllUsers():
        previousGame = getPreviousGame(user.battleTag)
        currentGame, data, err = await getCurrentGame(user.battleTag)

        if currentGame != previousGame and not err:
            embed = makeEmbed(data['name'], data['ratingIcon'], data['icon'])
            addfield("Tank", previousGame.tankRank, currentGame.tankRank)
            addfield("Damage", previousGame.damageRank, currentGame.damageRank)
            addfield("Support", previousGame.supportRank, currentGame.supportRank)
            saveGame(currentGame)
            plot = plotRank(user)
            plot.savefig("chart.png")
            chart = discord.File('chart.png', filename='chart.png')
            embed.set_image(url="attachment://chart.png")
            # Ensures the bot is connected before sending the message
            await bot.wait_until_ready()
            updateChannel = bot.get_channel(updateChannelID)
            await updateChannel.send(embed=embed, file=chart)
    cursor.close()


@slash.slash(name="linkprofile", description="Link a BattleNet account to your account", guild_ids=guild_ids,
             options=[create_option(name="battletag", description="Enter your BattleTag here!",
                                    option_type=discord_slash.SlashCommandOptionType.STRING, required=True)])
@commands.cooldown(1, 5.0, commands.BucketType.member)
async def _linkprofile(ctx, battletag: str):
    cursor = db.cursor(buffered=True)
    battletag = battletag.replace("#", "-")
    cursor.execute("select * from user where discordID = %s", (ctx.author.id,))
    # if user found
    if len(cursor.fetchall()):
        await ctx.send(content="You already have an account linked!")
        cursor.close()
        return

    data, error = await getProfile(battletag)
    if error:
        await ctx.send(content="This profile does not exist, or there was an unexpected error.")
        cursor.close()
        return

    if data['private']:
        await ctx.send("This profile is private, please set your profile to public in your Overwatch settings.")
        cursor.close()
        return

    tank, damage, support = getRanks(data)

    cursor.execute("insert into user (discordID,battleTag) values (%s, %s)", (ctx.author.id, battletag))
    db.commit()
    cursor.execute("insert into games (userID,tankRank,damageRank,supportRank,gameDate)"
                   " values (%s, %s, %s, %s, %s)",
                   (cursor.lastrowid, tank, damage, support, datetime.now()))
    db.commit()
    await ctx.send(content=f"{data['name']} successfully linked to your profile!")
    cursor.close()


@slash.slash(name="profile", description="Shows an Overwatch profile", guild_ids=guild_ids,
             options=[create_option(name="profile", description="Enter a BattleTag or tag a user here!",
                                    option_type=discord_slash.SlashCommandOptionType.STRING, required=False)])
@commands.cooldown(1, 2.0, commands.BucketType.member)
async def _profile(ctx, profile: str = ""):
    cursor = db.cursor(buffered=True)
    global battletag
    battletag = profile
    if profile == "":
        # No profile given, set authorid
        cursor.execute("select * from user where discordID = %s", (ctx.author.id,))
        userObjects = cursor.fetchall()
        if not len(userObjects):
            await ctx.send("You haven't linked an account yet.")
            cursor.close()
            return
        user = User(userObjects[0])
        battletag = user.battleTag
    elif profile.startswith("<@!") and profile.endswith(">"):
        # User tagged, remove tag
        profile = profile.lstrip("<@!")
        profile = profile.rstrip(">")
        cursor.execute("select * from user where discordID = %s", (profile,))
        userObjects = cursor.fetchall()
        if not len(userObjects):
            await ctx.send("This user has not linked an account yet.")
            cursor.close()
            return
        user = User(userObjects[0])
        battletag = user.battleTag
        cursor.close()
    battletag = battletag.replace("#", "-")

    data, error = await getProfile(battletag)
    if error:
        await ctx.send(content="This profile does not exist, or there was an unexpected error.")
        return

    if data['private']:
        await ctx.send("This profile is private")
        return
    elif data['ratings'] is None:
        await ctx.send("This profile does not have any competitive records for this season!")
        return

    embed = makeEmbed(data['name'], data['ratingIcon'], data['icon'])
    for field in range(len(data['ratings'])):
        embed.add_field(name=data['ratings'][field]['role'].capitalize(),
                        value=str(data['ratings'][field]['level']) + " SR", inline=False)
    await ctx.send(embed=embed)


@slash.slash(name="ping", description="This returns the ping of the bot.", guild_ids=guild_ids)
async def _ping(ctx):
    await ctx.send(content=f'Pong! {round(bot.latency * 1000)}ms', delete_after=10)


updateRanks = updateRanks.start()
bot.run(TOKEN)
