# imports
from json.encoder import INFINITY
import os
import math
from typing import Dict, List, Tuple
import requests
import json
import time
import threading
from io import BytesIO
from websocket import create_connection
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from PIL import ImageColor
from PIL import Image
import random


# function to convert rgb tuple to hexadecimal string
def rgb_to_hex(rgb: Tuple[int, int, int]):
    return ('#%02x%02x%02x' % rgb).upper()

def hex_to_rgb(hex: str) -> Tuple[int, int, int]:
    return ImageColor.getcolor(hex, "RGB")

# function to find the closest rgb color from palette to a target rgb color
def closest_color(target_rgb: Tuple[int, int, int], rgb_colors_array_in: List[Tuple[int, int, int]]):
    r, g, b = target_rgb
    color_diffs = []

    for color in rgb_colors_array_in:
        cr, cg, cb = color
        color_diff = math.sqrt((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2)
        color_diffs.append((color_diff, color))

    min_dist = (255*255*255)**2 # Distance can't be larger than that
    min_color = None
    for diff in color_diffs:
        if diff[0] < min_dist:
            min_dist = diff[0]
            min_color = diff[1]

    return min_color

# Gets BytesIO with the current /r/place board state
def get_board(access_token: str) -> Image:
    print("Getting board")
    ws = create_connection("wss://gql-realtime-2.reddit.com/query")
    ws.send(json.dumps({"type":"connection_init","payload":{"Authorization":"Bearer "+ access_token}}))
    ws.recv()
    ws.send(json.dumps({"id":"1","type":"start","payload":{"variables":{"input":{"channel":{"teamOwner":"AFD2022","category":"CONFIG"}}},"extensions":{},"operationName":"configuration","query":"subscription configuration($input: SubscribeInput!) {\n  subscribe(input: $input) {\n    id\n    ... on BasicMessage {\n      data {\n        __typename\n        ... on ConfigurationMessageData {\n          colorPalette {\n            colors {\n              hex\n              index\n              __typename\n            }\n            __typename\n          }\n          canvasConfigurations {\n            index\n            dx\n            dy\n            __typename\n          }\n          canvasWidth\n          canvasHeight\n          __typename\n        }\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"}}))
    ws.recv()
    ws.send(json.dumps({"id":"2","type":"start","payload":{"variables":{"input":{"channel":{"teamOwner":"AFD2022","category":"CANVAS","tag":"0"}}},"extensions":{},"operationName":"replace","query":"subscription replace($input: SubscribeInput!) {\n  subscribe(input: $input) {\n    id\n    ... on BasicMessage {\n      data {\n        __typename\n        ... on FullFrameMessageData {\n          __typename\n          name\n          timestamp\n        }\n        ... on DiffFrameMessageData {\n          __typename\n          name\n          currentTimestamp\n          previousTimestamp\n        }\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"}}))

    file = ""
    while True:
        temp = json.loads(ws.recv())
        if temp['type'] == 'data':
            msg = temp['payload']['data']['subscribe']
            if msg['data']['__typename'] == 'FullFrameMessageData':
                file = msg['data']['name']
                break


    ws.close()

    boardimg = BytesIO(requests.get(file, stream = True).content)
    current_board = Image.open(boardimg)
    rgb_current_board = current_board.convert('RGB')
    rgb_current_board.load()
    
    print("Got image:", file)

    return rgb_current_board

# method to read the input image.jpg file
def load_image():
    # read and load the image to draw and get its dimensions
    image_path = os.path.join(os.path.abspath(os.getcwd()), 'image.png')
    im = Image.open(image_path)
    im = im.convert('RGB')
    im.load()
    print("image size: ", im.size)  # Get the width and height of the image for iterating over
    image_width, image_height = im.size
    return (im, image_width, image_height)

def authenticate(username:str, password:str, app_client_id:str, secret_key:str):
    print("refreshing access token...")

    data = {
        'grant_type': 'password',
        'username': username,
        'password': password
    }

    r = requests.post("https://ssl.reddit.com/api/v1/access_token",
                        data=data,
                        auth=HTTPBasicAuth(app_client_id, secret_key),
                        headers={'User-agent': f'placebot{random.randint(1, 100000)}'})

    print("received response: ", r.text)

    response_data = r.json()
    access_token = response_data["access_token"]
    # access_token_type = response_data["token_type"]  # this is just "bearer"
    access_token_expires_in_seconds = response_data["expires_in"]  # this is usually "3600"
    # access_token_scope = response_data["scope"]  # this is usually "*"

    # ts stores the time in seconds
    current_timestamp = math.floor(time.time())
    access_token_expires_at_timestammp = current_timestamp + int(access_token_expires_in_seconds)

    print("received new access token: ", access_token)

    return (access_token, access_token_expires_at_timestammp)

# method to draw a pixel at an x, y coordinate in r/place with a specific color
def set_pixel(access_token_in: str, x: int, y: int, color_index_in: int):

    url = "https://gql-realtime-2.reddit.com/query"

    payload = json.dumps({
        "operationName": "setPixel",
        "variables": {
            "input": {
                "actionName": "r/replace:set_pixel",
                "PixelMessageData": {
                    "coordinate": {
                        "x": x,
                        "y": y
                    },
                    "colorIndex": color_index_in,
                    "canvasIndex": 0
                }
            }
        },
        "query": "mutation setPixel($input: ActInput!) {\n  act(input: $input) {\n    data {\n      ... on BasicMessage {\n        id\n        data {\n          ... on GetUserCooldownResponseMessageData {\n            nextAvailablePixelTimestamp\n            __typename\n          }\n          ... on SetPixelResponseMessageData {\n            timestamp\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n"
    })
    headers = {
        'origin': 'https://hot-potato.reddit.com',
        'referer': 'https://hot-potato.reddit.com/',
        'apollographql-client-name': 'mona-lisa',
        'Authorization': 'Bearer ' + access_token_in,
        'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    print("received response: ", response.text)

def find_incorrect_pixel(current_board_image: Image, target_image: Image, board_x: int, board_y: int, possible_colors: List[str]) -> Tuple[int, int, Tuple[int, int, int]]:
    rgb_possible_colors = [hex_to_rgb(c) for c in possible_colors]

    offset = 0

    all_incorrect_pixels = []
    for i in range(0, target_image.width):
        for j in range(0, target_image.height):
            target_image_pixel_rgb = target_image.getpixel((i,j))
            closest_target_image_pixel_rgb = closest_color(target_image_pixel_rgb, rgb_possible_colors)
            board_image_pixel_rgb = current_board_image.getpixel((i+board_x+offset,j+board_y+offset))
            if rgb_to_hex(board_image_pixel_rgb) != rgb_to_hex(closest_target_image_pixel_rgb):
                all_incorrect_pixels.append((i+board_x+offset, j+board_y+offset, closest_target_image_pixel_rgb))

    if len(all_incorrect_pixels) == 0:
        print("No incorrect pixels found")
        return None

    print(f"{len(all_incorrect_pixels)} pixels are incorrect")
    return random.choice(all_incorrect_pixels)


if __name__ == "__main__": 
    # load env variables
    load_dotenv()

    # map of colors for pixels you can place
    color_map = {
        "#FF4500": 2,  # bright red
        "#FFA800": 3,  # orange
        "#FFD635": 4,  # yellow
        "#00A368": 6,  # darker green
        "#7EED56": 8,  # lighter green
        "#2450A4": 12,  # darkest blue
        "#3690EA": 13,  # medium normal blue
        "#51E9F4": 14,  # cyan
        "#811E9F": 18,  # darkest purple
        "#B44AC0": 19,  # normal purple
        "#FF99AA": 23,  # pink
        "#9C6926": 25,  # brown
        "#000000": 27,  # black
        "#898D90": 29,  # grey
        "#D4D7D9": 30,  # light grey
        "#FFFFFF": 31,  # white
    }

    # color palette
    rgb_colors_array = []

    # auth variables
    access_token = ""
    access_token_expires_at_timestamp = 0 

    # image.jpg information
    target_image = None
    target_image_width = None
    target_image_height = None
    target_image, target_image_width, target_image_height = load_image()

    # place a pixel immediately
    first_run = True
    first_run_counter = 0

    # developer's reddit username and password
    username = os.getenv('ENV_PLACE_USERNAME')
    password = os.getenv('ENV_PLACE_PASSWORD')
    # note: use https://www.reddit.com/prefs/apps
    app_client_id = os.getenv('ENV_PLACE_APP_CLIENT_ID')
    secret_key = os.getenv('ENV_PLACE_SECRET_KEY')

    # The upper left corner on the /r/place board
    draw_x_start = int(os.getenv('ENV_DRAW_X_START'))
    draw_y_start = int(os.getenv('ENV_DRAW_Y_START'))

    access_token, access_token_expires_at_timestammp = authenticate(username, password, app_client_id, secret_key)

    # note: reddit limits us to place 1 pixel every 5 minutes, so I am setting it to
    # 5 minutes and 5 seconds per pixel
    pixel_place_frequency = 305
    last_time_placed_pixel = math.floor(time.time()) - pixel_place_frequency


    while True:
        time.sleep(1)
        # get the current time
        current_timestamp = math.floor(time.time())

        # log next time until drawing
        time_until_next_draw = last_time_placed_pixel + pixel_place_frequency - current_timestamp

        if time_until_next_draw <= 0:
            # Bingo! Time to draw a pixel
            # Check authentication
            if current_timestamp > access_token_expires_at_timestammp or access_token == "":
                print("Re-authenticating")
                access_token, access_token_expires_at_timestammp = authenticate(username, password, app_client_id, secret_key)

            # Find a pixel
            current_board = get_board(access_token)
            incorrect_pixel = find_incorrect_pixel(current_board, target_image, draw_x_start, draw_y_start, color_map.keys())

            if incorrect_pixel is None:
                continue

            board_x = incorrect_pixel[0]
            board_y = incorrect_pixel[1]
            proper_color = incorrect_pixel[2]

            proper_color_hex = rgb_to_hex(proper_color)
            color_index = color_map[proper_color_hex]

            # Place the pixel
            print("placing pixel with color " + proper_color_hex + " (" + str(color_index) + ") at " + str((board_x, board_y)))
            set_pixel(access_token, board_x, board_y, color_index)

            last_time_placed_pixel = math.floor(time.time())





