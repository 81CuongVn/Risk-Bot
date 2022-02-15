from replit import db
from display import draw_map
from keep_alive import keep_alive
import os
import discord
import random as r
import itertools
from copy import deepcopy

client = discord.Client()

#The list of continents can be a list since we never need to access them individually. 
#For territories, however, it is better to access them by name than by index.
continents = []
territories = {}
neighbours = {}

#Now let's fill up those empty containers above
with open("territories.txt") as file:
    continent = None
    for line in file:
      if line.startswith(">"):
        if continent: continents.append(continent)
        continent = {"name":line[1:-3].lower(),
                     "bonus":line[-2],
                     "territories":[]}
      else:
        text = line[:-1].split(" - ")
        name = text[0]
        continent["territories"].append(name)
        territories[name] = {"owner":None,
                             "troops":0}
        neighbours[name] = text[1].split(", ")
    continents.append(continent)

#Now for the functions. And we've got lots of 'em.

#Creates and returns a dictionary with game data.
def create_game(players, randomfill=False):

  game = {}

  #Initializing players
  deployable_troops = 0 if randomfill else (40, 35, 30, 25, 20)[len(players)-2]
  r.shuffle(players)
  game["players"] = {str(player_id):{"turn_number":i+1,
                                "colour":("red", "blue", "yellow", "green", "brown", "black")[i],
                                "territories":[],
                                "cards":[],
                                "deployable_troops":deployable_troops}
                     for i, player_id in enumerate(players)}

  #Initializing territories
  game["territories"] = deepcopy(territories)
  if randomfill:
    for key in game["territories"].keys():
      lucky_player = str(r.choice(players))
      territory = game["territories"][key]
      territory["owner"] = lucky_player
      territory["troops"] = r.randint(1, 10)
      game["players"][lucky_player]["territories"].append(key)
    player = game["players"][str(players[0])]
    player["deployable_troops"] = calculate_new_troops(player)

  #Initializing deck and discard pile
  territory_symbols = [_ for _ in territories.keys()]
  r.shuffle(territory_symbols)
  game["deck"] = [(("Infantry", "Cavalry", "Artillery")[i%3], territory_symbols[i]) for i in range(0, 42)] + [("Wild", None)]*2
  r.shuffle(game["deck"])
  game["discard_pile"] = []
      
  #Other variables
  game["turn_order"] = players.copy()
  game["active_player"] = 1
  game["eliminated_players"] = []
  game["turn_stage"] = 1
  game["in_pregame"] = False if randomfill else True
  game["unclaimed_territories"] = 0 if randomfill else 42
  game["last_attack"] = None
  game["card_claimed"] = False
  game["trade_count"] = 0

  return game


#Returns the id of the game which any given user is in.
def get_user_current_game_id(user):
  try:
    return db["users"][str(user.id)]["current_game_id"]
  except KeyError:
    db["users"][str(user.id)] = {"current_game_id":None}
    return db["users"][str(user.id)]["current_game_id"]


#Takes a player and calculates the number of new troops he receives.
def calculate_new_troops(player):

  #The number of territories you occupy.
  new_troops = len(player["territories"]) // 3
  if new_troops < 3: new_troops = 3

  #The value of the continents you control.
  for continent in continents:
    owns_continent = True
    for territory in continent["territories"]:
      if territory not in player["territories"]:
        owns_continent = False
        break
    if owns_continent:
      new_troops += int(continent["bonus"])
    
  return new_troops


#Ends current turn, starts next turn. Returns the id of the player whose turn it is.
def begin_next_player_turn(game):

  #Start by cycling active_player status to the next player
  while True:
    game["active_player"] += 1
    if game["active_player"] > len(game["players"]):
      game["active_player"] = 1
    if game["active_player"] in game["eliminated_players"]:
      continue
    break

  #Excuse this nightmare of an index
  player_id = game["turn_order"][game["active_player"]-1]
  player = game["players"][str(player_id)]

  if game["in_pregame"]:
    if player["deployable_troops"] == 0:
      game["in_pregame"] = False
    else: return player_id
  
  player["deployable_troops"] = calculate_new_troops(player)
  game["turn_stage"] = 1 if len(player["cards"]) < 5 else 0
  game["last_attack"] = None
  game["card_claimed"] = False

  return player_id


#Generates a message for the player whose turn it just became.
def generate_turn_start_message(game, player_id):

  troops = game["players"][str(player_id)]["deployable_troops"]

  if game["in_pregame"]:
    plural = "troops" if troops > 1 else "troop"
    message = f"It's your turn to deploy, <@{player_id}>. You have {troops} {plural} remaining."
  else:
    message = f"It's your turn, <@{player_id}>; you have {troops} new troops ready to be deployed." + (" But you have too many cards and must trade in a set before proceeding with your turn." if game["turn_stage"] == 0 else "")
  
  return message


#Now for the bot commands.

@client.event
async def on_ready():
  print(client.user, "has arrived.")

@client.event
async def on_message(message):

  if message.author == client.user:
    if message.content[:6] != "!hack ":
      return

  args = message.content.split()
  command = args[0]

  #Admin command that lets me use the bot like a test dummy player.
  if command == "!hack":
    if message.author == client.user:
      del args[0]
      command = args[0]
    elif message.author.id == int(os.environ['ADMIN_ID']):
      await message.channel.send(message.content)
      return

  if command == "!admin" and message.author.id == int(os.environ['ADMIN_ID']):
    if args[1] == "cleardb":
      db["games"] = []
      db["users"] = {}
      await message.channel.send("Database cleared.")
      return


  #The !play command. Starts a new game including the message sender and all mentioned players.
  if command == "!play":
    
    #Finding the users mentioned in the message in order to add them to the game
    players = message.mentions.copy()
    for mention in players:
      if message.author == mention:
        players.remove(mention)
    if len(players) == 0:
      await message.channel.send("Unfortunately you cannot play by yourself.")
      return
    if len(players) > 5:
      await message.channel.send("Too many players; the maximum is 6.")
      return
    players.append(message.author)

    #Checking to make sure none of the players are already in a game
    busy_players = []
    for player in players:
      if get_user_current_game_id(player) != None: busy_players.append(player.mention)
    if busy_players:
      await message.channel.send(f"{busy_players} is/are already in a game.")
      return

    #Turning the player list into a player id list
    players = [player.id for player in players]

    #Making the game, assigning the players to that game, updating the database
    game = None
    for i, g in enumerate(db["games"]):
      if g == None:
        x = i
        game = create_game(players, randomfill=bool(args[1] == "randomfill"))
        db["games"][i] = game
        break
    if not game:
      x = len(db["games"])
      game = create_game(players, randomfill=bool(args[1] == "randomfill"))
      db["games"].append(game)
    for player in players:
      db["users"][str(player)]["current_game_id"] = x
    db["games"][x]["index"] = x

    #Announcing the creation of a brand new game, yaaaaaaay
    announcement = f"New game created with id {x}.\n"
    for i, player in enumerate(players, 1):
      colour = ("red", "blue", "yellow", "green", "brown", "black")[i-1]
      announcement += f"Player {i} ({colour}): <@{player}>\n"
    await message.channel.send(announcement)
    await message.channel.send(generate_turn_start_message(game, players[0]))
    await message.channel.send(file=discord.File(draw_map(game), "map.jpg"))
    return


  #The !deploy command. Used by in-game players to place troops upon their territories.
  if command == "!deploy":
    
    user_current_game_id = get_user_current_game_id(message.author)

    #"NotInGameError"
    if user_current_game_id == None:
      await message.channel.send(f"You're not in a game, {message.author.mention}.")
      return

    user_id = str(message.author.id)
    game = db["games"][user_current_game_id]
    #"NotYourTurnError"
    if game["active_player"] != game["players"][user_id]["turn_number"]:
      await message.channel.send(f"It's not your turn, {message.author.mention}.")
      return
    #"NotYetDeploymentStageError"
    if game["turn_stage"] == 0:
      await message.channel.send(f"You must trade in a set of cards, {message.author.mention}. Type !trade to do so.")
      return
    #"DeploymentStageOverError"
    if game["turn_stage"] == 2:
      await message.channel.send(f"You have no troops left to deploy, {message.author.mention}.")
      return

    try: #This try block catches IndexErrors which could occur both in the try and except block of the following try-except statement.

      try: #This try block just catches ValueErrors, in case the user is using the shorter !deploy syntax which implies he only wants to deploy one troop.

        deployed_troops = int(args[1])
        if deployed_troops == 0: #"ZeroTroopError"
          await message.channel.send("You tried your hardest, and by a great force of will, you successfully deployed zero troops! So great was your power that you successfully deployed zero troops to not just one location, but every location! Wow! You're so going to win this war. And it's still your turn, by the way. As though you needed any more power.")
          return
        deploy_location = " ".join(args[2:]).title()

      except ValueError:
        deployed_troops = 1
        deploy_location = " ".join(args[1:]).title()

      #"TooManyTroopsError"
      if game["in_pregame"] and deployed_troops > 1:
        await message.channel.send("You can't deploy more than one troop at a time until the game setup is over.")
        return
      if game["players"][user_id]["deployable_troops"] < deployed_troops:
        await message.channel.send("You don't have that many troops.")
        return

    except IndexError:
      await message.channel.send("You didn't tell me where to deploy.")
      return
    
    #Alright, and NOW we can check to see if the user actually referenced a real territory lol
    try: territory = game["territories"][deploy_location]
    except KeyError as key:
      await message.channel.send(f"Couldn't find the territory '{key}'.")
      return
    if str(territory["owner"]) not in ("None", user_id): #"GetOffMyPropertyError"
      await message.channel.send("Someone else owns that territory.")
      return
    if game["unclaimed_territories"] and territory["owner"]: #"MustClaimTerritoryError"
      await message.channel.send("You must deploy on unclaimed territories while there are territories to be claimed.")
      return

    #Error checking finally finished. Deploying troops.
    if territory["owner"] == None:
      territory["owner"] = user_id
      game["unclaimed_territories"] -= 1
      game["players"][user_id]["territories"].append(deploy_location)

    territory["troops"] += deployed_troops
    game["players"][user_id]["deployable_troops"] -= deployed_troops

    await message.channel.send(f"Deployed {deployed_troops} " + ("troops" if deployed_troops > 1 else "troop") + f" to {deploy_location}.")

    #After deploying in the pregame, your turn immediately ends.
    if game["in_pregame"]:
      next_player_id = begin_next_player_turn(game)
      await message.channel.send(generate_turn_start_message(game, next_player_id))
      await message.channel.send(file=discord.File(draw_map(game), "map.jpg"))
      return

    #Done deploying all your troops? Right then, now you can use the attack command.
    if game["players"][user_id]["deployable_troops"] == 0:
      game["turn_stage"] = 2
      await message.channel.send("All troops deployed. Attack as you please, general.")
      await message.channel.send(file=discord.File(draw_map(game), "map.jpg"))
      return


  #The attack command. Self-explanatory.
  if command == "!attack":

    user_current_game_id = get_user_current_game_id(message.author)

    if user_current_game_id == None:
      await message.channel.send(f"You're not in a game, {message.author.mention}.")
      return

    user_id = str(message.author.id)
    game = db["games"][user_current_game_id]
    player = game["players"][user_id]

    if game["active_player"] != player["turn_number"]:
      await message.channel.send(f"It's not your turn, {message.author.mention}.")
      return
    if game["turn_stage"] != 2:
      troops = player["deployable_troops"]
      await message.channel.send(f"You must first deploy all of your troops, {message.author.mention}. You still have {troops} left.")
      return
    
    try:
      args[1]
      string = []
      for arg in args[1:]:
        if arg == "from":
          target = " ".join(string).title()
          if not target: raise NameError
          string = []
        elif arg == "with":
          if target:
            attacker = " ".join(string).title()
            if not attacker: raise NameError
            string = []
        else:
          string.append(arg)
      try:
        attacker
        army_size = int(string[0])
      except NameError:
        attacker = " ".join(string).title()
      target #checking if it exists
    
    #Might be using the shortcut
    except IndexError:
      if game["last_attack"]:
        target, attacker, army_size = game["last_attack"]
      else:
        await message.channel.send("Usage: !attack (target country) from (attacking country) [with (army size)]\n(e.g. !attack Siam from Indonesia with 2)\nAlternatively, !attack can be used on its own to repeat your previous attack. If you were attempting this, know that no previous attack was found.")
        return

    #Might just be doing it wrong
    except (NameError, ValueError):
      await message.channel.send("Invalid syntax. Usage: !attack (target country) from (attacking country) [with (army size)]\n(e.g. !attack Siam from Indonesia with 2)")
      return

    #We should have values for target and attacker, and possibly for army_size
    try: army_size
    except NameError: army_size = 3
    
    #Checking that the attack is legal
    try:
      def_territory = game["territories"][target]
      def_territory_troops = def_territory["troops"]
      off_territory = game["territories"][attacker]
      off_territory_troops = off_territory["troops"]
    except KeyError as key:
      await message.channel.send(f"Couldn't find the territory '{key}'.")
      return
    if off_territory["owner"] != user_id:
      await message.channel.send("You can't attack from a territory you don't own.")
      return
    if target not in neighbours[attacker]:
      await message.channel.send("Those territories are not adjacent.")
      return
    if def_territory["owner"] == user_id:
      await message.channel.send("You can't attack yourself.")
      return
    if off_territory_troops == 1:
      await message.channel.send("You can't attack with one troop; doing so would leave your territory undefended.")
      return
    
    #Automatically adjusting army size if necessary
    adjusted = False
    if army_size > 3:
      army_size = 3
      adjusted = True
    if off_territory_troops <= army_size:
      army_size = off_territory_troops - 1
      adjusted = True
    if adjusted:
      await message.channel.send(f"Automatically reducing attacking army size to {army_size}...")
    
    #Calling defenders to arms
    def_size = 2 if def_territory["troops"] > 1 else 1
    
    off_dice = [r.randint(1, 6) for die in range(0, army_size)]
    def_dice = [r.randint(1, 6) for die in range(0, def_size)]
    off_dice.sort(reverse=True)
    def_dice.sort(reverse=True)
    off_dead = 0
    def_dead = 0
    try:
      for i in range(0, 2):
        if off_dice[i] > def_dice[i]: def_dead += 1
        else: off_dead += 1
    except IndexError: pass

    those_who_lost = "both armies" if off_dead and def_dead else "attackers" if off_dead else "defenders"
    amount_text = "two troops" if 2 in (off_dead, def_dead) else "one troop"
    
    changes = "("
    if those_who_lost != "defenders":
      changes += f"{off_territory_troops} -> {off_territory_troops - off_dead}"
      if those_who_lost == "both armies":
        changes += ", "
    if those_who_lost != "attackers":
      changes += f"{def_territory_troops} -> {def_territory_troops - def_dead}"
    changes += ")"

    results = f"Rolling...\n`Attackers ({off_territory_troops}): {off_dice}`\n`Defenders ({def_territory_troops}): {def_dice}`\n`Result: {those_who_lost} lose {amount_text}. {changes}`"

    off_territory["troops"] -= off_dead
    def_territory["troops"] -= def_dead
    game["last_attack"] = (target, attacker, army_size)

    if def_territory["troops"] == 0:

      conquered_player_id = def_territory["owner"]
      conquered_player = game["players"][conquered_player_id]
      conquered_player["territories"].remove(target)

      if len(conquered_player["territories"]) == 0: #Player eliminated.
        game["discard_pile"] += conquered_player["cards"]
        conquered_player["cards"] = None
        game["eliminated_players"].append(conquered_player["turn_number"])
        results += f"\n\n<@{conquered_player_id}> has been eliminated."
        db["users"][conquered_player_id]["current_game_id"] = None
      
      max_troops = off_territory["troops"] - 1
      min_troops = army_size - off_dead
      def_territory["owner"] = user_id
      def_territory["troops"] = min_troops
      off_territory["troops"] -= min_troops

      game["players"][user_id]["territories"].append(target)
      #Check for victory
      if len(game["players"][user_id]["territories"]) == 42:
        results += f"\n\nVICTORY! <@{user_id}> has conquered the world!"
        await message.channel.send(results)
        await message.channel.send(file=discord.File(draw_map(game), "map.jpg"))
        db["users"][user_id]["current_game_id"] = None
        db["games"][game["index"]] = None
        return

      results += f"\n\nYou've conquered {target}! {min_troops} of your troops were automatically moved forward into that territory for you."
      if max_troops != min_troops:
        if max_troops - min_troops == 1:
          results += f" But you can also type '!move' to move an additional 1 troop forward. (Doing some other move or attack will negate this opportunity.)"
        else:
          results += f" But you can also type '!move' to move {max_troops - min_troops} additional troops forward (the maximum), or '!move (number)' to move a specific, lesser number of additional troops forward. (Doing some other move or attack will negate this opportunity.)"
      else:
        game["last_attack"] = None

      if not game["card_claimed"]:
        player["cards"].append(game["deck"].pop())
        game["card_claimed"] = True
        results += "\n\nFor conquering a territory this turn, you also gained a card."

    elif off_territory["troops"] == 1:
      results += f"\n\nYour army has grown too small to continue the attack."

    await message.channel.send(results)
    if def_territory["owner"] == user_id or off_territory["troops"] == 1:
      await message.channel.send(file=discord.File(draw_map(game), "map.jpg"))
    return


  if command == "!move":
    
    user_current_game_id = get_user_current_game_id(message.author)

    if user_current_game_id == None:
      await message.channel.send(f"You're not in a game, {message.author.mention}.")
      return

    user_id = str(message.author.id)
    game = db["games"][user_current_game_id]
    player = game["players"][user_id]

    if game["active_player"] != player["turn_number"]:
      await message.channel.send(f"It's not your turn, {message.author.mention}.")
      return
    if game["turn_stage"] != 2:
      troops = player["deployable_troops"]
      await message.channel.send(f"You must first deploy all of your troops, {message.author.mention}. You still have {troops} left.")
      return

    #Putting this message here is better than wrapping the following block of code in one fat try statement and catching arbitrary SyntaxErrors
    move_command_syntax_error_message = "Invalid syntax. Usage: '!move (number of troops) from (starting territory) to (destination territory)'\n(e.g. '!move 5 from Egypt to Middle East')\nAfter conquering a territory, !move is also used to move more troops into the conquered territory, like so: '!move 5'."

    #Checking to see if this is a move into a just-conquered territory.
    try: args[2]
    except IndexError:
      if not game["last_attack"]:
        try: args[1]
        except IndexError:
          await message.channel.send("Usage: '!move (number of troops) from (starting territory) to (destination territory)'\n(e.g. '!move 5 from Egypt to Middle East')\nAfter conquering a territory, !move is also used to move more troops into the conquered territory, like so: '!move 5'.")
          return
      
      target, attacker, _ = game["last_attack"]
      target_territory = game["territories"][target]
      attacker_territory = game["territories"][attacker]

      if target_territory["owner"] != attacker_territory["owner"]:
        await message.channel.send("You haven't conquered the territory yet.")
        return
          
      try:
        troop_count = int(args[1])
        if attacker_territory["troops"] <= troop_count:
          await message.channel.send("You're trying to move too many troops; one troop must always stay behind.")
          return
      except IndexError: #No first argument
        troop_count = attacker_territory["troops"] - 1
      except ValueError: #First argument was not an integer. Unacceptable.
        await message.channel.send(move_command_syntax_error_message)
        return
          
      attacker_territory["troops"] -= troop_count
      target_territory["troops"] += troop_count
      game["last_attack"] = None

      target_troops = target_territory["troops"]
      plural = "s" if troop_count > 1 else ""
      await message.channel.send(f"Moved {troop_count} extra troop{plural} to {target}, increasing its troop count to {target_troops}.")
      return
    
    #Now for parsing the end-of-turn-movement syntax
    try:
      troop_count = int(args[1])
      if args[2] != "from": raise ValueError #sure, call me cheap
    except ValueError:
      await message.channel.send(move_command_syntax_error_message)
      return
    
    #Extracting the rest of the arguments
    try:
      string = []
      for arg in args[3:]:
        if arg == "to":
          start = " ".join(string).title()
          if not start: raise NameError
          string = []
        else: string.append(arg)
      start
      destination = " ".join(string).title()
      if not destination: raise NameError
    except (NameError, IndexError):
      await message.channel.send(move_command_syntax_error_message)
      return

    #Checking that the move is legal
    try:
      territory_a = game["territories"][start]
      territory_b = game["territories"][destination]
    except KeyError as key:
      await message.channel.send(f"Couldn't find the territory '{key}'.")
      return
    if territory_a["owner"] != user_id:
      await message.channel.send(f"You don't own {start}.")
      return
    elif territory_b["owner"] != user_id:
      await message.channel.send(f"You don't own {destination}.")
      return
    if start not in neighbours[destination]:
      await message.channel.send("Those territories are not adjacent.")
      return
    if troop_count >= territory_a["troops"]:
      await message.channel.send("You're trying to move too many troops: at least one troop must always stay behind.")
      return
    
    territory_a["troops"] -= troop_count
    territory_b["troops"] += troop_count

    destination_troops = territory_b["troops"]
    await message.channel.send(f"Moved {troop_count} extra troops to {destination}, increasing its troop count to {destination_troops}.")

    #Starting the next player's turn.
    start_message = generate_turn_start_message(game, begin_next_player_turn(game))
    await message.channel.send(start_message)
    await message.channel.send(file=discord.File(draw_map(game), "map.jpg"))
    return


  #The !cards command lets players see their cards.
  if command == "!cards":

    user_current_game_id = get_user_current_game_id(message.author)
    if user_current_game_id == None:
      await message.channel.send(f"You're not in a game, {message.author.mention}.")
      return

    cards = db["games"][user_current_game_id]["players"][str(message.author.id)]["cards"]
    display = "Your cards:"
    for card in cards:
      territory = card[1]
      if card[0] == "Infantry":
        display += f"\n> [:military_helmet: - {territory}]"
      elif card[0] == "Cavalry":
        display += f"\n> [:horse: - {territory}]"
      elif card[0] == "Artillery":
        display += f"\n> [:boom: - {territory}]"
      else:
        display += "\n> [:military_helmet: - :horse: - :artillery: - Wild]"

    await message.channel.send(display)
    return


  #The !trade command lets players trade in their cards. Automatically selects the remaining cards if some or all of the cards are unspecified.
  if command == "!trade":

    user_current_game_id = get_user_current_game_id(message.author)
    user_id = str(message.author.id)

    if user_current_game_id == None:
      await message.channel.send(f"You're not in a game, {message.author.mention}.")
      return

    game = db["games"][user_current_game_id]

    if game["active_player"] != game["players"][user_id]["turn_number"]:
      await message.channel.send(f"It's not your turn, {message.author.mention}.")
      return
    if game["turn_stage"] == 2:
      await message.channel.send(f"You've deployed all your troops and therefore can no longer trade, {message.author.mention}.")
      return

    player = game["players"][user_id]
    cards = player["cards"]

    if len(cards) < 3:
      await message.channel.send(f"You don't have enough cards to trade, {message.author.mention}.")
      return

    selected_cards = []
    try:
      for i in range(1, 5):

        try: card_index = int(args[i])-1 #Card numbers start at 1, not 0
        except IndexError: break #All arguments recorded, moving on
        
        #Exceptions
        except ValueError: #TheNumberGreenError
          await message.channel.send("Invalid syntax; use numbers (no commas) to indicate which cards you're trading. (e.g. !trade 1 2 4)")
          return
        if card_index < 0: raise IndexError #NegativeIndexError
        if i == 4: #TooManyArgumentsError
          await message.channel.send("There are only three cards to a set. Why are you trying to trade in four?")
          return

        selected_cards.append(cards[card_index]) #Legit card? Alright then.

    except IndexError as i:
      if i < 21 and i > -1:
        await message.channel.send(f"You don't have a {i}th card, mate.")
      else:
        await message.channel.send(f"Don't be absurd. No one has {i} cards.")
      return

    #Just a helpful inner function
    def check_set_legality(cards_to_be_checked):
      legal = False
      if len(cards_to_be_checked) == 3:
        L = [card[0] for card in cards_to_be_checked]
        L, wild = (L.count("Infantry"), L.count("Cavalry"), L.count("Artillery")), L.count("Wild")
        if wild or L.count(2) == 0: legal = True
      return legal

    #Legality checking and autoselecting
    if len(selected_cards) == 3:
      if not check_set_legality(selected_cards):
        await message.channel.send("That's not a legal set of cards.")
        return
    else: #Autoselecting
      #Filling a list named legal_sets with all possible legal sets of cards
      legal_sets = []
      unselected_cards = [card for card in cards if card not in selected_cards]
      for combination in itertools.combinations(unselected_cards, 3 - len(selected_cards)):
        possible_set = selected_cards + list(combination)
        if check_set_legality(possible_set):
          legal_sets.append(possible_set)
      if not legal_sets:
        await message.channel.send(f"You don't have a complete set to trade in, {message.author.mention}.")
        return

    #If we haven't selected yet, that means we have multiple legal sets to choose from
    if len(selected_cards) != 3:
      scores = [] #for storing how good each set is
      
      #Calculating set scores
      for legal_set in legal_sets:
        score = 0
        card_types = []

        for card in legal_set:
          if card[0] == "Wild": card_types.append("Wild")
          elif card[1] in player["territories"]: card_types.append("Bonus")
          else: card_types.append("Normal")
        
        #The criteria for the best set? 1. Set has a bonus card. 2. Set has a low number of wild cards. 3. Set has a low number of bonus cards.
        if "Bonus" in card_types: score += 3
        wilds = card_types.count("Wild")
        if wilds:
          if wilds == 1: score += 1
        else: score += 2
        if score == 5: score += card_types.count("Normal")

        scores.append(score)
      
      selected_cards = legal_sets[scores.index(max(scores))]

    bonus_territory = None
    for card in selected_cards:
      if not bonus_territory and card[1] in player["territories"]:
        bonus_territory = card[1]
      cards.remove(card)
      game["discard_pile"].append(card)

    #Success! Have some troops
    try: new_troops = (4, 6, 8, 10, 12, 15)[game["trade_count"]]
    except IndexError: new_troops = ((game["trade_count"]-2)*5) #20, 25, 30...
    game["trade_count"] += 1
    player["deployable_troops"] += new_troops
    deployable_troops = player["deployable_troops"]
    
    #If a bonus card was traded in, drop two bonus troops on that territory
    if bonus_territory: game["territories"][bonus_territory]["troops"] += 2

    await message.channel.send(f"You've received {new_troops} extra troops and now have {deployable_troops} troops left to deploy." + (f" (Additionally, for trading in a card marked with {bonus_territory}, a territory you own, two extra troops were deployed to {bonus_territory}.)" if bonus_territory else ""))
    if game["turn_stage"] == 0: game["turn_stage"] = 1
    return


  #Displays the game's map.
  if command == "!map":
    user_current_game_id = get_user_current_game_id(message.author)
    if user_current_game_id == None:
      await message.channel.send(f"You're not in a game, {message.author.mention}.")
      return
    await message.channel.send(file=discord.File(draw_map(db["games"][user_current_game_id]), "map.jpg"))
    return


  #Ends the player's turn.
  if command == "!endturn":

    user_current_game_id = get_user_current_game_id(message.author)

    if user_current_game_id == None:
      await message.channel.send(f"You're not in a game, {message.author.mention}.")
      return

    user_id = str(message.author.id)
    game = db["games"][user_current_game_id]
    player = game["players"][user_id]

    if game["active_player"] != player["turn_number"]:
      await message.channel.send(f"It's not your turn, {message.author.mention}.")
      return
    if game["turn_stage"] != 2:
      troops = player["deployable_troops"]
      await message.channel.send(f"You must first deploy all of your troops, {message.author.mention}. You still have {troops} left.")
      return

    start_message = generate_turn_start_message(game, begin_next_player_turn(game))
    await message.channel.send(start_message)
    await message.channel.send(file=discord.File(draw_map(game), "map.jpg"))
    return


  if command == "!resign":

    user_current_game_id = get_user_current_game_id(message.author)

    if user_current_game_id == None:
      await message.channel.send(f"You're not in a game, {message.author.mention}.")
      return

    user_id = str(message.author.id)
    game = db["games"][user_current_game_id]
    player = game["players"][user_id]

    game["discard_pile"] += player["cards"]
    player["cards"] = None
    game["eliminated_players"].append(player["turn_number"])
    
    await message.channel.send(f"<@{user_id}> has resigned.")
    if len(game["players"]) == len(game["eliminated_players"]) + 1:
      winner_id = begin_next_player_turn(game)
      await message.channel.send(f"\n\nVICTORY! <@{winner_id}> has conquered the world! (Or most of it, anyway.)")
      await message.channel.send(file=discord.File(draw_map(game), "map.jpg"))
      db["users"][user_id]["current_game_id"] = None
      db["games"][game["index"]] = None
      return
      
    elif game["active_player"] == player["turn_number"]:
      start_message = generate_turn_start_message(game, begin_next_player_turn(game))
      await message.channel.send(start_message)
      await message.channel.send(file=discord.File(draw_map(game), "map.jpg"))
    return



keep_alive()
client.run(os.environ['TOKEN'])