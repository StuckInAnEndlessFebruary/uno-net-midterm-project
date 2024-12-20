import socket
import threading
import os
from uno_game import UnoGame, UnoCard, UnoPlayer

HOST = '127.0.0.1'
PORT = 65432

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen()

clients = {}
game = None
save_file = "saved_game.txt"

USER_CREDENTIALS_FILE = "user_credentials.txt"

user_credentials = {}
game_history = {}

def load_user_credentials():
    if os.path.exists(USER_CREDENTIALS_FILE):
        with open(USER_CREDENTIALS_FILE, 'r') as file:
            for line in file:
                data = line.strip().split(',')
                username, password = data[0], data[1]
                wins, losses = int(data[2]), int(data[3])
                user_credentials[username] = password
                game_history[username] = {"wins": wins, "losses": losses}

def save_user_credentials():
    with open(USER_CREDENTIALS_FILE, 'w') as file:
        for username, password in user_credentials.items():
            wins = game_history[username]["wins"]
            losses = game_history[username]["losses"]
            file.write(f"{username},{password},{wins},{losses}\n")

def save_game():
    with open(save_file, 'w') as file:
        file.write(f"{game.current_card.color}:{game.current_card.card_type}\n")
        for player in game.players:
            hand = '|'.join([f"{card.color}:{card.card_type}" for card in player.hand])
            file.write(f"{player.player_id},{hand}\n")
        file.write(','.join(clients.keys()) + '\n')
        file.write(f"{game.current_player.player_id}\n")

def load_game():
    global game, clients
    with open(save_file, 'r') as file:
        lines = file.readlines()
        current_card = string_to_card(lines[0].strip())
        players = []
        for line in lines[1:-2]:
            parts = line.strip().split(',')
            player_id = int(parts[0])
            hand = [string_to_card(card) for card in parts[1].split('|')]
            players.append(UnoPlayer(hand, player_id))
        clients = {username: None for username in lines[-2].strip().split(',')}
        current_player_id = int(lines[-1].strip())
        
        game = UnoGame(players=len(players))
        game.current_card = current_card
        game.players = players
        game._current_player = next(player for player in players if player.player_id == current_player_id)

def card_to_string(card):
    return f"{card.color}:{card.card_type}"

def string_to_card(data):
    color, card_type = data.split(':')
    return UnoCard(color, card_type)

load_user_credentials()

def handle_client(client_socket):
    global game
    try:
        while True:
            client_socket.send("Enter 1 to Sign Up, 2 to Log In, or 3 to Load Game:".encode('utf-8'))
            choice = client_socket.recv(1024).decode('utf-8').strip()
            
            if choice == '1':
                client_socket.send("Enter a username:".encode('utf-8'))
                username = client_socket.recv(1024).decode('utf-8').strip()
                
                client_socket.send("Enter a password:".encode('utf-8'))
                password = client_socket.recv(1024).decode('utf-8').strip()
                
                if username in user_credentials:
                    client_socket.send("Username already exists. Try logging in.".encode('utf-8'))
                else:
                    user_credentials[username] = password
                    game_history[username] = {"wins": 0, "losses": 0}
                    save_user_credentials()
                    client_socket.send("Sign Up successful. You can log in now.".encode('utf-8'))
            
            elif choice == '2':
                client_socket.send("Enter username:".encode('utf-8'))
                username = client_socket.recv(1024).decode('utf-8').strip()

                client_socket.send("Enter password:".encode('utf-8'))
                password = client_socket.recv(1024).decode('utf-8').strip()

                if username in user_credentials and user_credentials[username] == password:
                    clients[username] = client_socket
                    wins = game_history[username]["wins"]
                    losses = game_history[username]["losses"]
                    client_socket.send(f"Login successful. Wins: {wins}, Losses: {losses}".encode('utf-8'))
                    break
                else:
                    client_socket.send("Invalid credentials. Try again.".encode('utf-8'))

            elif choice == '3':
                if os.path.exists(save_file):
                    load_game()
                    client_socket.send("Game loaded successfully.".encode('utf-8'))
                    break
                else:
                    client_socket.send("No saved game available.".encode('utf-8'))

        if game is None:
            game = UnoGame(players=2)
            
        if len(clients) == len(game.players):
            broadcast_game_state()
            manage_game()

    except Exception as e:
        print(f"Error: {e}")
        client_socket.close()

def manage_game():
    for username, client_socket in clients.items():
        player_id = list(clients.keys()).index(username)
        threading.Thread(target=game_loop, args=(client_socket, username, player_id)).start()

def game_loop(client_socket, username, player_id):
    global game
    while True:
        try:
            message = client_socket.recv(1024).decode('utf-8')
            if not message:
                break
            print(f"Received message from {username}: {message}")
            if message.lower() == 'exit':
                client_socket.send("Do you want to save the game? (yes/no):".encode('utf-8'))
                save_choice = client_socket.recv(1024).decode('utf-8').strip().lower()
                if save_choice == 'yes':
                    save_game()
                    client_socket.send("Game saved successfully.".encode('utf-8'))
                client_socket.send("Goodbye!".encode('utf-8'))
                client_socket.close()
                clients[username] = None
                return
            elif message.isdigit():
                card_index = int(message)
                if game.current_player == game.players[player_id]:
                    card = game.players[player_id].hand[card_index]
                    try:
                        if card.color == 'black':
                            while True:
                                client_socket.send("Choose a new color: 1. Red 2. Yellow 3. Green 4. Blue".encode('utf-8'))
                                color_choice = client_socket.recv(1024).decode('utf-8').strip()
                                color_dict = {'1': 'red', '2': 'yellow', '3': 'green', '4': 'blue'}
                                if color_choice in color_dict:
                                    new_color = color_dict[color_choice]
                                    card.temp_color = new_color
                                    game.play(player_id, card_index, new_color)
                                    broadcast(f"Color changed to {new_color}", client_socket, username)
                                    broadcast_game_state()
                                    break
                                else:
                                    client_socket.send("Invalid choice. Please enter a valid number: 1, 2, 3, or 4.".encode('utf-8'))
                        else:
                            game.play(player_id, card_index)
                            broadcast_game_state()
                            if game.winner:
                                update_game_history(game.winner.player_id)
                                announce_winner(game.winner.player_id)
                                reset_game()
                    except ValueError as e:
                        client_socket.send(f"Error: {e}. Please enter a valid card index:".encode('utf-8'))
            elif message.lower() == 'draw':
                if game.current_player == game.players[player_id]:
                    game.play(player_id, card=None)
                    broadcast_game_state()
                    # Check if the drawn card is playable
                    if game.players[player_id].can_play(game.current_card):
                        client_socket.send("You can play the drawn card. Enter the card index to play it.".encode('utf-8'))
                    else:
                        # next_player()
                        broadcast_game_state()
                else:
                    client_socket.send("Invalid move: not your turn".encode('utf-8'))
            else:
                broadcast(message, client_socket, username)
        except Exception as e:
            print(f"Error: {e}")
            if client_socket:
                client_socket.close()
            clients[username] = None
            break

def broadcast(message, client_socket=None, username=None):
    for client_username, client in clients.items():
        if client != client_socket:
            try:
                client.send(f"Received message from {username}: {message}".encode('utf-8'))
            except Exception as e:
                print(f"Error broadcasting to {client_username}: {e}")
                client.close()
                clients[client_username] = None

def broadcast_game_state():
    for i, (username, client) in enumerate(clients.items()):
        hand = ' '.join(str(card) for card in game.players[i].hand)
        current_card = game.current_card
        current_color = current_card.temp_color if current_card.color == 'black' else current_card.color
        message = f"Your hand: {hand}\nCurrent card: {current_card} (Color: {current_color})\nCurrent player: {game.current_player.player_id}"
        try:
            client.send(message.encode('utf-8'))
        except:
            client.close()

def next_player():
    game.__next__()
    broadcast_game_state()

def update_game_history(winner_player_id):
    # جستجو برای نام کاربری برنده با استفاده از player_id
    winner_username = None
    for username, player in zip(clients.keys(), game.players):
        if player.player_id == winner_player_id:
            winner_username = username
            break

    # به‌روزرسانی تاریخچه بازی
    for username in clients.keys():
        if username == winner_username:
            game_history[username]["wins"] += 1
        else:
            game_history[username]["losses"] += 1

    save_user_credentials()



def announce_winner(winner_id):
    for client in clients.values():
        client.send(f"Player {winner_id} wins the game!".encode('utf-8'))

def reset_game():
    global game
    game = UnoGame(players=2)
    broadcast_game_state()

def start_server():
    print(f"Server started on {HOST}:{PORT}")
    while True:
        client_socket, client_address = server_socket.accept()
        print(f"New connection from {client_address}")
        thread = threading.Thread(target=handle_client, args=(client_socket,))
        thread.start()

start_server()
