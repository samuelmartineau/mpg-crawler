import sys
print(sys.version)

import pip
import re
import os
import sqlite3
import time
import unicodedata

# CONST
MPG_CALENDARS = 'http://www.monpetitgazon.com/calendrier-resultat-championnat.php?num=%d'
BASE_URL = 'http://www.monpetitgazon.com'
DETAILS_URL = '/DetailMatchChampionnat2.php'
NUMBER_OF_GAMES = 38
DB_FILE = 'mpg.db'
CURRENT_DIRECTORY = os.getcwd()
PLAYERS_FILE_PATH = os.path.join(CURRENT_DIRECTORY, 'players.html')
LOG_FILE_PLAYER_NOT_FOUND = 'players-not-found.txt'

# DB
try:
    os.remove(DB_FILE)
except OSError:
    pass
try:
    os.remove(LOG_FILE_PLAYER_NOT_FOUND)
except OSError:
    pass

conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

# Create table
c.execute('''CREATE TABLE player
             (id INTEGER PRIMARY KEY, transfertFee INTEGER, position TEXT, firstName TEXT, familyName TEXT, team TEXT, UNIQUE(firstName, familyName, team))''')

c.execute('''CREATE TABLE game
             (id INTEGER PRIMARY KEY, gameLabel TEXT, gameDay INTEGER, awayTeam TEXT, homeTeam TEXT, homeScore INTEGER, awayScore INTEGER)''')

c.execute('''CREATE TABLE goal
             (game INTEGER, scorer TEXT, FOREIGN KEY(scorer) REFERENCES player(id), FOREIGN KEY(game) REFERENCES game(id))''')

c.execute('''CREATE TABLE mark
             (player TEXT, substitute INTEGER DEFAULT 0, game INTEGER, mark INTEGER, FOREIGN KEY(player) REFERENCES player(id), FOREIGN KEY(game) REFERENCES game(id))''')

def install(package):
    pip.main(['install', package])

def strip_accents(s):
   return ''.join(c for c in unicodedata.normalize('NFD', s)
                  if unicodedata.category(c) != 'Mn')

def clean_name(playerName):
    return strip_accents(playerName).lower()

install('BeautifulSoup4')

from urllib.request import urlopen
from bs4 import BeautifulSoup

def loadPlayers():
    print("Load Players")
    playersHtml = open(PLAYERS_FILE_PATH)
    soup = BeautifulSoup(playersHtml, 'html.parser')

    playerElements = soup.find('tbody').findAll('tr')
    for playerElement in playerElements:
        playerInfos = playerElement.findAll('td')
        position = playerInfos[0].text
        familyName = clean_name(playerInfos[1].text)
        firstName = clean_name(playerInfos[2].text)
        team = playerInfos[3].text
        transfertFee = playerInfos[4].text

        c.execute('INSERT INTO player (position, familyName, firstName, team, transfertFee) VALUES (?, ?, ?, ?, ?)', (position, familyName, firstName, team, transfertFee))

def loadGames():
    print("Load Games")
    for gameDay in range(1, NUMBER_OF_GAMES + 1):
        print("Championship day %d" % gameDay)
        mpgCalendarsHtml = urlopen(MPG_CALENDARS % gameDay)
        soup = BeautifulSoup(mpgCalendarsHtml, 'html.parser')
        detailsGamesLinks = soup.findAll('a', href = re.compile(DETAILS_URL + '.*'))

        for link in detailsGamesLinks:
            gameDetailsUrl = link.get('href')
            gameDetailsHtml = urlopen(BASE_URL + gameDetailsUrl)
            soup = BeautifulSoup(gameDetailsHtml, 'html.parser')

            featuredEvent = soup.find('div', class_='featured-event')
            gameLabel = featuredEvent.find('h2').text
            teamPattern = re.compile('([A-Za-z]+\-?[A-Za-z]+)')
            teams = teamPattern.findall(gameLabel)
            scorePattern = re.compile('(\d)')
            scores = scorePattern.findall(gameLabel)

            homeTeam = teams[0]
            homeScore = scores[0]
            awayScore = scores[1]
            awayTeam = teams[1]
            print("Game %s" % gameLabel)

            c.execute('INSERT INTO game (gameLabel, gameDay, awayTeam, homeTeam, homeScore, awayScore) VALUES (?, ?, ?, ?, ?, ?)', (gameLabel, gameDay, awayTeam, homeTeam, homeScore, awayScore))
            gameId = c.lastrowid

            wayClasses = ['teamhome', 'teamaway']

            for idx, wayClasse in enumerate(wayClasses):

                for blockIndex in range(0, 2):
                    playersElements = soup.findAll('div', class_=wayClasse)[blockIndex].findAll('div', class_='joueur')

                    for player in playersElements:
                        team = homeTeam if idx == 0 else awayTeam

                        familyName = clean_name(player.findChildren()[-1].text)
                        if familyName: # possibly a substitute so empty
                            c.execute('SELECT id FROM player WHERE familyName = ? OR firstName || \' \' || familyName = ? AND team = ? ORDER BY transfertFee DESC;', (familyName, familyName, team))
                            result = c.fetchone()
                            if result:
                                playerId = result[0]

                                mark = player.find('div', class_='note').find('p').text
                                c.execute('INSERT INTO mark (player, game, mark, substitute) VALUES (?, ?, ?, ?)', (playerId, gameId, mark, blockIndex))

                                goalsBlock = player.find('div', class_='but').findAll('img')
                                goals = len(goalsBlock) if goalsBlock else 0
                                mark = player.find('div', class_='note').find('p').text

                                for i in range(0, goals):
                                    c.execute('INSERT INTO goal (scorer, game) VALUES (?, ?)', (playerId, gameId))
                            else:
                                with open(LOG_FILE_PLAYER_NOT_FOUND, 'a') as myfile:
                                    myfile.write('Player not found %s %s\n' % (familyName, team))

loadPlayers()
loadGames()

# Save (commit) the changes
conn.commit()

# We can also close the connection if we are done with it.
# Just be sure any changes have been committed or they will be lost.
conn.close()
