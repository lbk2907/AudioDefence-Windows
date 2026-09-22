"""The two text views of ADAboutCreditsViewController, as the iPhone nib (tag 2781) holds them.

Extracted from ADAboutCreditsViewController.nib: the about text is object #76, the credits text object #25.
"""

ABOUT_TEXT = 'Remember, using headphones at excessive volume can injure your ears.\n\nAudio Defence: Zombie Arena uses binaural audio to render a 3D world using only sound. You play with your ears, so you’ll need headphones - any old pair will do, just make sure you wear the right way in the right ears.\n\nFor the most immersive experience we recommend Gyro Mode: stand up and  point the device in the direction you want to aim and you’ll hear the game world turn with you. If that’s not practical for you, try Swipe mode, where you drag your finger left or right on the screen to turn, or Tilt mode, where you tilt your device sideways to turn in either direction.\n\nAlso for a more immersive experience, we recommend Gesture mode, which will allow you to play without having to worry about button placement on the screen.\n\nYou can configure your Aiming and Layout options in the Settings menu and anytime in game by pausing it.'

CREDITS_TEXT = '\nwww.audiodefence.com\n\nOriginal Idea & Game Design\nAntoine Pastor\n\nProducers\nCarles Salas\nPeter Law\n\nLevel Design\nCarles Salas\n\nWriting\nCarles Salas\n\nLead Developer\nAntoine Pastor\n\nLead Engineer\nNigel James Brown\n\nAdditional Programmer\nDaniel J. Finnegan\n\nTechnical Product Manager\nNeville Daniel\n\nArt Direction\nHeyBigMan Studios\n\nGraphic Designer\nFrancisco Torres\nDavid Aldhouse\n\nSound Design\nAdele Cutting\nJames Locke-Hart\nEd de Lacy\nJoe Brammall\nJohn Scott\n\nMusic\nKenny Zhao\n\nJukebox Music\nJoe Brammall\n\nVOICE CAST\nDr. Bastard\nOliver Dismal\n\nAnnouncer\nFenella Fudge\n\nZombies & Crowds\nAntoine Pastor\nCarles Salas\nTom Green\nNicky Birch\nRob McHardy\nEd de Lacy\nTrevor Klein\nHowie Shannon\nOliver Smyth\nAdam Goodwin\nJames Austin\nBecci Ride\nJonathon Bartley\nJoby Waldman\nClaire White\nMiranda Hinkley\nMegan Croft\nNick Read\nZosia Morris\n\nSound Recording and Editing\nEd DeLacy\nManish Doolabh\nJoe Brammall\nJohn Scott\n\nChief Creative Officer\nPaul Bennun\n\nExecutive Producers\nNicky Birch\nTom Green\n\nHead of Product and Marketing\nNicky Birch \n\nGame Design Consultant\nSander van der Vegte\n\nSpecial thanks to:\nSarah Haake\nJonathon Bartley\nAmi Bennet\nLucy Duffiel'

#: PORT ADDITION: the nib's credits name everyone who made the game, and the game's own website, but never
#: the studio.  This goes above them, so the screen says whose game it is before it says who made it.
STUDIO_TEXT = """Audio Defence: Zombie Arena
by Somethin' Else
"""

#: PORT ADDITION: who made the Windows and Mac port, in the shape the original's credits use - the role, then the
#: names under it.  It is a text view of its own, read after the original's, so nobody has to walk through
#: the whole cast to reach it or past it.
PORT_CREDITS_TEXT = """The Windows and Mac port

github.com/lbk2907/AudioDefence-Windows

Ported by
Loh Boon Keat
Muhammad Hajjar

Written by
Claude Opus 5

Original Idea
Muhammad Hajjar

Testing
Wong Wee Xiang

Built from the game's own code, method by method. The game itself - its audio, its writing, its design -
is Somethin' Else's, and this port only carries it to a keyboard."""
