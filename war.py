"""
war card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
import socketserver
import threading
import sys


"""
Namedtuples work like classes, but are much more lightweight so they end
up being faster. It would be a good idea to keep objects in each of these
for each game which contain the game's state, for instance things like the
socket, the cards given, the cards still available, etc.

p1, p2: clients
p1deck, p2deck: list[int] -- each player can only play cards in their deck
p1played, p2played: list[int] -- can't replay an already-played card
sock: socket

Score is handled on client side
"""
Game = namedtuple("Game", 'p1 p2 p1deck p2deck p1next p2next p1score p2score turn sock')

# Stores the clients waiting to get connected to other clients
waiting_clients = []


class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3

class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2

def readexactly(sock: socket.socket, numbytes: int):
    """
    TODO: Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """
    b = sock.recv(numbytes)
    logging.debug('Received bytes: %s', str(b))
    return b

def kill_game(game):
    """
    TODO: If either client sends a bad message, immediately nuke the game.
    """
    game = namedtuple("Game", 'p1 p2 p1deck p2deck p1next p2next p1score p2score turn sock')

def compare_cards(card1: int, card2: int):
    """
    Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    # Copy these because we're about to change them
    raw_card1 = card1
    raw_card2 = card2
    # Apply mod 13 to the cards to remove suit
    card1 %= 13
    card2 %= 13
    # Add 2 to card values so logs are more readable
    card1 += 2
    card2 += 2
    # Fold J/Q/K into 10
    if card1 in (11, 12, 13):
        card1 = 10
    if card2 in (11, 12, 13):
        card2 = 10
    # Change ace to 11 (à la blackjack), again for readability
    if card1 == 14:
        card1 = 11
    if card2 == 14:
        card2 = 11
    # Final comparison
    if card1 > card2:
        logging.debug('P1|%d|%d  >  P2|%d|%d', 
                     raw_card1, card1, raw_card2, card2)
        return 1
    elif card1 < card2:
        logging.debug('P1|%d|%d  <  P2|%d|%d', 
                     raw_card1, card1, raw_card2, card2)
        return -1
    else:
        logging.debug('P1|%d|%d  =  P2|%d|%d', 
                     raw_card1, card1, raw_card2, card2)
        return 0

def deal_cards():
    """
    Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    deck = range(52)
    random.shuffle(deck)
    logging.debug('Shuffled deck')
    return (deck[0:26], deck[26:52])

def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    

async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)

async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0

def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(loop)
        
    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()

if __name__ == "__main__":
    # Changing logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1:])
