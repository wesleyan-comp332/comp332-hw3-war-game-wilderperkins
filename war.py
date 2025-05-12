"""
war card game client and server
"""
import asyncio
# from collections import namedtuple
from enum import Enum
import logging
import random
import socket
import socketserver
# import threading
import sys


# namedtuples may be faster on performance, 
# but they sure aren't faster for me to code with!
# Game = namedtuple("Game", 'p1sock p2sock p1addr p2addr \
# p1deck p2deck p1play p2play discard turn')
class Game:
    def __init__(self, p1sock, p2sock, p1addr, p2addr, p1deck, p2deck, p1play, p2play, discard, turn):
        self.p1sock : socket.socket = p1sock
        self.p2sock : socket.socket = p2sock
        self.p1addr : tuple[str, int] = p1addr
        self.p2addr : tuple[str, int] = p2addr
        self.p1deck : list[int] = p1deck 
        self.p2deck : list[int] = p2deck
        self.p1play : int = p1play
        self.p2play : int = p2play
        self.discard : list[int] = discard
        self.turn : bool = turn
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
    If either client sends a bad message, immediately nuke the game.
    """
    game.p1sock.close()
    game.p2sock.close()
    logging.debug('Sockets closed')
    games.remove(game)
    logging.info('Game removed')

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
        server = socketserver.TCPServer((host, port), WarHandler)
        server.timeout = .1
        while True:
            logging.debug('  ==== Loop ====  ')
            # Need to call separately instead of using handle_request
            # because we need to keep the socket and address
            if len(games) == 0:
                (sock, addr) = server.get_request()
                logging.debug('sock: %s', sock)
                logging.debug('addr: %s', addr)
            elif games[0].turn: # i.e. if p2's turn
                sock = games[0].p2sock
                addr = games[0].p2addr
                games[0].turn = not games[0].turn
            else: # i.e. if p1's turn
                sock = games[0].p1sock
                addr = games[0].p1addr
                games[0].turn = not games[0].turn

            try:
                raw_read = readexactly(sock, 1)
            except OSError: # if socket closed, readexactly will fail
                kill_game(games[0])

            if len(raw_read) == 0:
                kill_game(games[0])
                continue
            req_type = int(raw_read[0])
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
                    pass
                    # kill_game(g)
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
                        g = Game(p1sock, p2sock,
                                p1sock.getpeername(), p2sock.getpeername(),
                                decks[0], decks[1], None, None, [], False)
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
                    logging.debug('Card ID %d', card_id)

                    # Cards must be in interval [0, 51]
                    if card_id < 0 or card_id > 51:
                        logging.warning('Invalid card id %d', card_id)
                        kill_game(g)
                        continue

                    # No reusing already-played cards
                    if card_id in g.discard:
                        logging.warning('Card id %d already used', card_id)
                        kill_game(g)
                        continue

                    # Assign card to correct player
                    if p1:
                        g.p1play = card_id
                    else:
                        g.p2play = card_id
                    logging.debug('Current plays: %s, %s', g.p1play, g.p2play)

                    # If we have both players' cards, compare them
                    # and send back who won
                    if g.p1play is not None and g.p2play is not None:
                        # No playing cards that were never in your deck 
                        # to begin with
                        if g.p1play not in g.p1deck:
                            logging.warning('%d not in p1 deck', g.p1play)
                            kill_game(g)
                            continue
                        if g.p2play not in g.p2deck:
                            logging.warning('%d not in p2 deck', g.p2play)
                            kill_game(g)
                            continue

                        result = compare_cards(g.p1play, g.p2play)
                        # 1 = p1 wins
                        # -1 = p2 wins
                        # 0 = tie
                        if result == 1:
                            logging.debug('%s > %s, p1 wins',
                                            g.p1play, g.p2play)
                            g.p1sock.sendall(bytes([Command.PLAYRESULT.value,
                                                    Result.WIN.value]))
                            g.p2sock.sendall(bytes([Command.PLAYRESULT.value,
                                                    Result.LOSE.value]))
                        elif result == -1:
                            logging.debug('%s < %s, p2 wins',
                                            g.p1play, g.p2play)
                            g.p1sock.sendall(bytes([Command.PLAYRESULT.value,
                                                    Result.LOSE.value]))
                            g.p2sock.sendall(bytes([Command.PLAYRESULT.value,
                                                    Result.WIN.value]))
                        else: # 0
                            logging.debug('%s = %s, tie',
                                            g.p1play, g.p2play)
                            g.p1sock.sendall(bytes([Command.PLAYRESULT.value,
                                                    Result.DRAW.value]))
                            g.p2sock.sendall(bytes([Command.PLAYRESULT.value,
                                                    Result.DRAW.value]))
                        # Regardless, we need to clear stuff
                        g.discard.extend([g.p1play, g.p2play])
                        g.p1play = None
                        g.p2play = None

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
        server.server_close()
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

async def client(host, port, _): # loop unused
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
            logging.debug('Result: %s', result)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
            logging.debug('Score: %d', myscore)
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.info("Game complete, I %s", result)
        writer.close()
        logging.info('writer close')
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.IncompleteReadError:
        logging.error("asyncio.IncompleteReadError")
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
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
