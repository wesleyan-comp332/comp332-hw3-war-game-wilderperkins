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
# import threading
import sys


"""
Namedtuples work like classes, but are much more lightweight so they end
up being faster. It would be a good idea to keep objects in each of these
for each game which contain the game's state, for instance things like the
socket, the cards given, the cards still available, etc.

p1sock, p2sock: socket
p1addr, p2addr: tuple[str, int]
p1deck, p2deck: list[int] - each player can only play cards in their deck
p1play, p2play: int|None - store card each player wants to play till we get both
discard: list[int] - list already-played cards to block their reuse

Score is handled on client side
"""
Game = namedtuple("Game", 'p1sock p2sock p1addr p2addr \
p1deck p2deck p1play p2play discard')
games = []

# Stores the clients waiting to get connected to other clients
waiting_clients : list[socket.socket] = []


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
    logging.info('TODO: kill_game')

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
    deck = list(range(52))
    random.shuffle(deck)
    logging.debug('Shuffled deck')
    return (deck[0:26], deck[26:52])

def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    try:
        with socketserver.TCPServer((host, port), WarHandler) as server:
            while True:
                print('==== Loop ====')
                # Need to call separately instead of using handle_request
                # because we need to keep the socket and address
                (sock, addr) = server.get_request()
                logging.debug('sock: %s', sock)
                logging.debug('addr: %s', addr)

                req_type = int(readexactly(sock, 1)[0])
                logging.debug('req_type: %s (%s)', req_type, Command(req_type))

                if Command(req_type) == Command.WANTGAME:
                    # Reject if client already in game
                    # TODO: Multithreading ignores any requests not involving
                    # either of the two clients (detect with sock/addr)
                    ingame = False
                    g = None
                    for g in games:
                        if addr in (g.p1addr, g.p2addr):
                            ingame = True
                            break
                    logging.debug('0 ingame: %s', ingame)

                    if ingame:
                        kill_game(g)
                    else:
                        # Add client to waiting room if they're not there already
                        if sock not in waiting_clients:
                            waiting_clients.append(sock)
                            logging.debug('Added %s to waiting room', sock)
                            logging.debug('%d clients in waiting room: %s', 
                                        len(waiting_clients), waiting_clients)

                        if len(waiting_clients) >= 2:
                            # If 2+ clients waiting, start game with the first 2 
                            # members of waiting_clients
                            decks = deal_cards()
                            p1sock : socket.socket = waiting_clients.pop(0)
                            p2sock : socket.socket = waiting_clients.pop(0)# was index 1
                            print(p1sock, p2sock)
                            g = Game(p1sock, p2sock,
                                    p1sock.getpeername(), p2sock.getpeername(),
                                    decks[0], decks[1], None, None, [])
                            logging.info('New game between %s and %s', 
                                        g.p1addr, g.p2addr)
                            games.append(g)
                            # Send GAMESTART message to clients
                            g.p1sock.sendall(
                                bytes([Command.GAMESTART.value]+g.p1deck))
                            logging.debug('P1 deck sent: %s',
                                decks[0])
                            g.p2sock.sendall(
                                bytes([Command.GAMESTART.value]+g.p2deck))
                            logging.debug('P2 deck sent: %s',
                                decks[1])

                elif Command(req_type) == Command.PLAYCARD and len(games) > 0:
                    # Only if in game
                    ingame = False
                    g = games[0] # just to make the linter stop whining that
                                # g might be undefined
                    for g in games:
                        logging.debug('test')
                        if addr in (g.p1addr, g.p2addr):
                            ingame = True
                            break
                    logging.debug('2 ingame: %s', ingame)

                    if ingame:
                        # Based on when we break, g will have the correct clients
                        # Now, figure out which player number this is
                        if sock == g.p1sock:
                            p1 = True
                        else:
                            p1 = False

                        # Payload = card ID (0 to 51)
                        card_id = int(readexactly(sock, 1)[0])

                        if p1:
                            g.p1play = card_id
                        else:
                            g.p2play = card_id

                        # If we have both players' cards, compare them
                        # and send back who won
                        if g.p1play is not None and g.p2play is not None:
                            result = compare_cards(g.p1play, g.p2play)
                            # 1 = p1 wins
                            # -1 = p2 wins
                            # 0 = tie
                            if result == 1:
                                g.p1sock.sendall(bytes([Command.PLAYRESULT.value,
                                                        Result.WIN.value]))
                                g.p2sock.sendall(bytes([Command.PLAYRESULT.value,
                                                        Result.LOSE.value]))
                            elif result == -1:
                                g.p1sock.sendall(bytes([Command.PLAYRESULT.value,
                                                        Result.LOSE.value]))
                                g.p2sock.sendall(bytes([Command.PLAYRESULT.value,
                                                        Result.WIN.value]))
                            else: # 0
                                g.p1sock.sendall(bytes([Command.PLAYRESULT.value,
                                                        Result.DRAW.value]))
                                g.p2sock.sendall(bytes([Command.PLAYRESULT.value,
                                                        Result.DRAW.value]))
                    else:
                        # If request is sent and we aren't in game at all,
                        # request is invalid
                        logging.warning('Bad request %d: %s isn’t in a game', 
                                        req_type, addr)
                        kill_game(g)
                else: # the other commands are sent by the server to the client
                    logging.warning('Bad request %d', req_type)
                    kill_game(g)
    except KeyboardInterrupt:
        return
    
class WarHandler(socketserver.BaseRequestHandler):
    def handle(self):
        pass

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
        logging.debug('Card msg: %s', list(card_msg))
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            logging.debug('Played card: %d', card)
            result = await reader.readexactly(2)
            logging.debug('Result: %d', result)
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
        logging.debug('writer close')
        return 1
    # except ConnectionResetError:
    #     logging.error("ConnectionResetError")
    #     return 0
    except asyncio.IncompleteReadError:
        logging.error("asyncio.IncompleteReadError")
        return 0
    # Commenting out so I can see the actual error msg
    # except OSError:
    #     logging.error("OSError")
    #     return 0

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
        finally:
            pass
        
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
    logging.debug('loop close')

if __name__ == "__main__":
    # Changing logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1:])
