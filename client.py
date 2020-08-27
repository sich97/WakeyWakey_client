"""
File: client.py

This program lets you change settings as well as shut the alarm off once it's started.
"""

import configparser
import socket
import ast
import platform
import os
import time
import tkinter
import random
import numpy as np
import pyautogui
import sys

SETTINGS_PATH = "settings.ini"
MIN_LINE_LENGTH = 5
LINE_THICKNESS = 8
BORDER_MARGIN = 10
WINDOW_TITLE_MARGIN = 33


def main():
    """
    After initialization, the program branches into two cases; One in which the alarm is on and you'll be able to
    turn it off by succeeding the awake test. And another in which the alarm is off and you'll be able to change
    settings, such as wakeup time, UTC offset, and more.
    :return: None
    """
    # Initialization
    server_address, server_port, window_height, window_width, alarm_state = initialize()

    # If the alarm is on
    if alarm_state == 1:

        # Test if the user is awake
        awake_test(window_height, window_width)

        # After having completed the awoke_test properly, stop the alarm
        set_alarm_state(server_address, server_port, 0)

        sys.exit()

    # If the server is not in alarm mode
    elif alarm_state == 0:

        # Go into management mode
        management(server_address, server_port)

        sys.exit()


"""
########################################################################################################################
                                                        INITIALIZATION
########################################################################################################################
"""


def initialize():
    """
    Loads settings from settings.ini and gets the current state of the alarm.
    :return: server_address (str), server_port(int), window_height (int), window_width (int), alarm_state (int)
    """
    # Load settings from settings.ini
    server_address, server_port, window_height, window_width = load_settings()

    # Get server state
    alarm_state = get_alarm_state(server_address, server_port)

    return server_address, server_port, window_height, window_width, alarm_state


def load_settings():
    """
    Loads settings.ini and returns its information.
    :return: server_address (str), server_port (str), window_height (int), window_width (int)
    """
    # Load settings.ini
    config = configparser.ConfigParser()
    config.read(SETTINGS_PATH)
    config.sections()
    server_address = config['SERVER']['Address']
    server_port = config['SERVER']['Port']
    window_height = int(config['CLIENT']['Window height'])
    window_width = int(config['CLIENT']['Window width'])

    return server_address, server_port, window_height, window_width


"""
########################################################################################################################
                                                        AWAKE TEST
########################################################################################################################
"""


def awake_test(window_height, window_width):
    """
    Gives the user challenges until one is overcome, in which case we assume the user is awake enough to not fall back
    to sleep.
    :param window_height: How many pixels high the GUI should be.
    :type window_height: int
    :param window_width: How many pixels wide the GUI should be.
    :type window_width: int
    :return: None
    """
    # Create GUI
    window, canvas = create_awake_test_gui(window_height, window_width)

    # Create test
    start, east_lines, west_lines, south_lines, north_lines = create_test(canvas)

    # Run tests
    awake = tkinter.BooleanVar(canvas, False, "awake")
    while not awake.get():
        awake.set(run_test(canvas, start))

    print("Congratulations. You passed the test!")


def create_awake_test_gui(window_height, window_width):
    """
    Creates the GUI
    :param window_height: How many pixels high the GUI should be.
    :type window_height: int
    :param window_width: How many pixels wide the GUI should be.
    :type window_width: int
    :return: window (tkinter.Tk), canvas (tkinter.Canvas)
    """
    # Sets minimum window height
    if window_height < 36:
        window_height = 36
    # Sets minimum window width
    if window_width < 36:
        window_width = 36

    # Creating the main window
    window = tkinter.Tk()
    window.geometry(str(window_width) + "x" + str(window_height) + "+0+0")
    window.minsize(height=window_height, width=window_width)
    window.title("Wakey Wakey - Awake test")

    # The canvas that the cells are drawn onto
    canvas = tkinter.Canvas(window, height=window_height, width=window_width, bg="white")

    canvas.grid(row=0, column=0)
    canvas.update()

    return window, canvas


def create_test(canvas):
    """
    Fills the canvas with a graphical test, and a success condition.
    :param canvas: The GUI in which the test is drawn onto.
    :type canvas: tkinter.Canvas
    :return: east_lines (list of tkinter.Canvas.create_rectangle), west_lines (list of tkinter.Canvas.create_rectangle),
    south_lines (list of tkinter.Canvas.create_rectangle), north_lines (list of tkinter.Canvas.create_rectangle)
    """
    # Choose which side the mouse pointer shall start on (Left: 1, Top: 2)
    start_side = random.randint(1, 2)

    size = np.array([canvas.winfo_width() - 3 - BORDER_MARGIN, canvas.winfo_height() - 3 - BORDER_MARGIN])

    # Create start and end
    if start_side == 1:
        # If starting side is left
        start = np.array([BORDER_MARGIN, random.randint(BORDER_MARGIN, size[1])])
        canvas.create_rectangle(start[0], start[1], start[0] + LINE_THICKNESS * 2, start[1] + LINE_THICKNESS * 2,
                                fill="green", outline="green")

        end = np.array([size[0], random.randint(BORDER_MARGIN, size[1])])
        end_block = canvas.create_rectangle(end[0], end[1], end[0] - LINE_THICKNESS * 2, end[1] + LINE_THICKNESS * 2,
                                            fill="red", outline="red")

    else:
        # If starting side is top
        start = np.array([random.randint(BORDER_MARGIN, size[0]), BORDER_MARGIN])
        canvas.create_rectangle(start[0], start[1], start[0] + LINE_THICKNESS * 2, start[1] + LINE_THICKNESS * 2,
                                fill="green", outline="green")

        end = np.array([random.randint(BORDER_MARGIN, size[0]), size[1]])
        end_block = canvas.create_rectangle(end[0], end[1], end[0] + LINE_THICKNESS * 2, end[1] - LINE_THICKNESS * 2,
                                            fill="red", outline="red")

    # Instantiate list for referencing lines by their direction
    east_lines = []
    west_lines = []
    south_lines = []
    north_lines = []

    # Create start line
    line_end, previous_direction, path_complete = draw_line(start, end, size, canvas, end_block,
                                                            [0, 0], east_lines, west_lines, south_lines, north_lines)
    canvas.update()

    # While the previous line doesn't touch the goal
    while not path_complete:
        # Draw a new line
        line_end, previous_direction, path_complete = draw_line(line_end, end, size, canvas, end_block,
                                                                previous_direction, east_lines, west_lines,
                                                                south_lines, north_lines)
        canvas.update()

    # After the path is complete, increase the thickness of all the lines
    east_lines, west_lines, south_lines, north_lines = increase_line_thickness(canvas, east_lines, west_lines,
                                                                               south_lines, north_lines,
                                                                               LINE_THICKNESS)

    return start, east_lines, west_lines, south_lines, north_lines


def draw_line(start, end, size, canvas, end_block, previous_direction,
              east_lines, west_lines, south_lines, north_lines):
    """
    Draws a line in such a way as to make a connection between start and end.
    :param start: Where the line will have to start.
    :type start: np.array
    :param end: Where the new line will try to get closer to.
    :type end: np.array
    :param size: The width and height of the game area.
    :type size: np.array
    :param canvas: The GUI in which the challenge happens.
    :type canvas: tkinter.TK
    :param end_block: The area in which any pixel marks the goal, and the end of any new line.
    :type end_block: tkinter.Canvas.create_rectangle
    :param previous_direction: The direction in which the previous line was headed.
    :type previous_direction: np.array
    :param east_lines: An array containing a reference to all the lines going east.
    :type east_lines: list
    :param west_lines: An array containing a reference to all the lines going west.
    :type west_lines: list
    :param south_lines: An array containing a reference to all the lines going south.
    :type south_lines: list
    :param north_lines: An array containing a reference to all the lines going north.
    :type north_lines: list
    :return: line_end (np.array), direction (np.array), covers_goal (boolean)
    """
    # Get direction
    direction = determine_direction(start, end, previous_direction)

    # Get line length
    max_direction_length = np.multiply(size, direction)
    max_direction_length = max_direction_length[max_direction_length != 0]
    max_direction_length = abs(int(max_direction_length[0]))
    random_line_length = random.randint(MIN_LINE_LENGTH, max_direction_length)

    # Calculate line end
    line_end = np.add(start, np.multiply(direction, random_line_length))
    if line_end[0] > size[0] or line_end[0] < BORDER_MARGIN:
        line_end[0] = size[0]
    if line_end[1] > size[1] or line_end[1] < BORDER_MARGIN:
        line_end[1] = size[1]

    # Draw line in the determined direction
    if direction[0] == 1:
        east_lines.append(canvas.create_rectangle(start[0], start[1], line_end[0], line_end[1],
                                                  fill="black"))
    elif direction[0] == -1:
        west_lines.append(canvas.create_rectangle(start[0], start[1], line_end[0], line_end[1],
                                                  fill="black"))
    elif direction[1] == 1:
        south_lines.append(canvas.create_rectangle(start[0], start[1], line_end[0], line_end[1],
                                                   fill="black"))
    elif direction[1] == -1:
        north_lines.append(canvas.create_rectangle(start[0], start[1], line_end[0], line_end[1],
                                                   fill="black"))

    # Check if the new line overlaps the goal
    if end_block in canvas.find_overlapping(start[0], start[1], line_end[0], line_end[1]):
        covers_goal = True
    else:
        covers_goal = False

    return line_end, direction, covers_goal


def determine_direction(source, destination, previous_direction):
    """
    Determines the cardinal direction that gives the shortest path between point a (source) and b (destination)
    :param source: Point A
    :type source: np.array
    :param destination: Point B
    :type destination: np.array
    :param previous_direction: The direction which was last used.
    :type previous_direction: np.array
    :return: np.array
    """
    # Find vector from source to destination
    direct_path = np.subtract(destination, source)

    # Return most impacting direction as a scalar vector
    if abs(direct_path[0]) >= abs(direct_path[1]):
        if direct_path[0] >= 0:
            direction = np.array([1, 0])
        else:
            direction = np.array([-1, 0])
    else:
        if direct_path[1] >= 0:
            direction = np.array([0, 1])
        else:
            direction = np.array([0, -1])

    # Get the opposite direction of the previous one
    opposite_of_previous_direction = previous_direction
    opposite_of_previous_direction = opposite_of_previous_direction[opposite_of_previous_direction != 0] * -1

    # If the proposed new direction is perpendicular to the previous one, go south
    if np.array_equal(direction, previous_direction) or np.array_equal(direction, opposite_of_previous_direction):
        x = direction[0]
        y = direction[1]
        direction = np.array([y, x])

    return direction


def increase_line_thickness(canvas, east_lines, west_lines, south_lines, north_lines, increase_factor):
    """
    Increases the thickness of all drawn lines.
    :param canvas: The GUI in which the challenge happens.
    :type canvas: tkinter.TK
    :param east_lines: An array containing a reference to all the lines going east.
    :type east_lines: list
    :param west_lines: An array containing a reference to all the lines going west.
    :type west_lines: list
    :param south_lines: An array containing a reference to all the lines going south.
    :type south_lines: list
    :param north_lines: An array containing a reference to all the lines going north.
    :type north_lines: list
    :param increase_factor: How many pixels to increase the line thickness by.
    :type increase_factor: int
    :return: new_east_lines (list), new_west_lines (list), new_south_lines (list), new_north_lines (list)
    """
    # Instantiate the lists which will contain references to the new, thicker, lines.
    new_east_lines = []
    new_west_lines = []
    new_south_lines = []
    new_north_lines = []

    # Go through each line going in this direction, draw a new line which is thicker, then delete the old one
    for line in east_lines:
        x0, y0, x1, y1 = canvas.coords(line)
        y1 += increase_factor
        x1 += increase_factor

        canvas.delete(line)
        new_east_lines.append(canvas.create_rectangle(x0, y0, x1, y1, fill="black"))

    # Clear the old list of the thinner lines going in this direction
    east_lines.clear()

    # Go through each line going in this direction, draw a new line which is thicker, then delete the old one
    for line in west_lines:
        x0, y0, x1, y1 = canvas.coords(line)
        y1 += increase_factor
        x1 += increase_factor

        canvas.delete(line)
        new_west_lines.append(canvas.create_rectangle(x0, y0, x1, y1, fill="black"))

    # Clear the old list of the thinner lines going in this direction
    west_lines.clear()

    # Go through each line going in this direction, draw a new line which is thicker, then delete the old one
    for line in south_lines:
        x0, y0, x1, y1 = canvas.coords(line)
        y1 += increase_factor
        x1 += increase_factor

        canvas.delete(line)
        new_south_lines.append(canvas.create_rectangle(x0, y0, x1, y1, fill="black"))

    # Clear the old list of the thinner lines going in this direction
    south_lines.clear()

    # Go through each line going in this direction, draw a new line which is thicker, then delete the old one
    for line in north_lines:
        x0, y0, x1, y1 = canvas.coords(line)
        y1 += increase_factor
        x1 += increase_factor

        canvas.delete(line)
        new_north_lines.append(canvas.create_rectangle(x0, y0, x1, y1, fill="black"))

    # Clear the old list of the thinner lines going in this direction
    north_lines.clear()

    canvas.update()

    return new_east_lines, new_west_lines, new_south_lines, new_north_lines


def run_test(canvas, start):
    """
    Runs the awake test.
    :param canvas: The GUI in which the test is drawn onto.
    :type canvas: tkinter.Canvas
    :param start: The coordinates of the start position of the challenge.
    :type start: np.array
    :return: success (boolean)
    """
    # Place mouse pointer over start_block
    pyautogui.moveTo(start[0] + LINE_THICKNESS // 2, start[1] + 33 + LINE_THICKNESS // 2)

    success = False

    # While the mouse hasn't yet reached the goal
    while not success:
        canvas.update()

        # Check mouse position
        mouse_x, mouse_y = pyautogui.position()
        mouse_y -= WINDOW_TITLE_MARGIN

        # Check pixel color of mouse position
        current_pixel_color = get_pixel_color(canvas, mouse_x, mouse_y)

        if current_pixel_color == "WHITE":
            # Touching wall
            print("You have touched the wall! Moving you back to start.")
            pyautogui.moveTo(start[0] + LINE_THICKNESS // 2, start[1] + WINDOW_TITLE_MARGIN + LINE_THICKNESS // 2)
            time.sleep(0.1)

        # Check if in goal
        elif current_pixel_color == "RED":
            # Reached goal
            print("You have reached the goal!")
            success = True

        # To avoid huge system load
        else:
            time.sleep(0.1)

    return success


def get_pixel_color(canvas, x, y):
    """
    Gets the pixel color of a certain pixel in a canvas.
    :param canvas: The canvas in question.
    :type canvas: tkinter.Canvas
    :param x: The x coordinate of the pixel to check.
    :type x: int
    :param y: The y coordinate of the pixel to check.
    :type y: int
    :return: string
    """
    # Get a list og the canvas objects overlapping the given coordinate
    ids = canvas.find_overlapping(x, y, x, y)

    # Instantiate list which will contain the color of all the overlapping widgets
    colors = []

    if len(ids) > 0:
        for index in ids:
            color = canvas.itemcget(index, "fill")
            color = color.upper()
            if color != '':
                colors.append(color)

    # Returns a color in the following priority: Red, Green, Black, White
    if "RED" in colors:
        return "RED"
    elif "GREEN" in colors:
        return "GREEN"
    elif "BLACK" in colors:
        return "BLACK"
    else:
        return "WHITE"


"""
########################################################################################################################
                                                        MANAGEMENT
########################################################################################################################
"""


def get_alarm_state(server_address, server_port):
    """
    Returns the value of alarm_state, which is stored in the database on the server.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :return: alarm_state (int)
    """
    connection = server_connection(server_address, server_port)

    # Request alarm state
    command = "get_alarm_state"
    connection.send(bytes(command, "utf-8"))

    # Receive and decode response
    msg = connection.recv(1024)
    msg_decoded = msg.decode("utf-8")
    alarm_state = int(msg_decoded)

    # Close connection
    connection.close()

    return alarm_state


def server_connection(server_address, server_port):
    """
    Creates a server connection and returns the socket.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :return: s (socket.socket)
    """
    # Create an INET streaming socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connect to the server
    s.connect((server_address, int(server_port)))

    # Return the socket
    return s


def set_alarm_state(server_address, server_port, new_alarm_state):
    """
    Sets the value of alarm_state, which is stored in the database on the server.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :param new_alarm_state: The requested new value of alarm_state.
    :type new_alarm_state: int
    :return: None
    """
    # Connect to server
    connection = server_connection(server_address, server_port)

    # Request changing alarm state
    command = "set_alarm_state " + str(new_alarm_state)
    connection.send(bytes(command, "utf-8"))

    # Close connection
    connection.close()


def management(server_address, server_port):
    """
    Shows the current user preferences stored on server.
    Then lets the user change them.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :return: None
    """
    system = platform.system()
    not_done = True

    # While the user is not done changing settings
    while not_done:
        # Clear the console
        if system == "Windows":
            os.system("cls")
        else:
            os.system("clear")

        # Display current preferences
        user_preferences = load_user_preferences(server_address, server_port)
        display_user_preferences(user_preferences)

        # Changing preferences
        preference_to_change = get_input("Input the number of the setting you wish to change: ", "int", 2)

        # If changing active_state
        if preference_to_change == 1:
            current_active_state = user_preferences["active_state"]
            change_active_state(server_address, server_port, current_active_state)

        # If changing wakeup time
        elif preference_to_change == 2:
            print("Changing wakeup time.")
            new_wakeup_hour = get_input("Please input hour: ", "int", 0)
            new_wakeup_minute = get_input("Please input minute: ", "int", 0)

            change_wakeup_time(server_address, server_port, "hour", new_wakeup_hour)
            change_wakeup_time(server_address, server_port, "minute", new_wakeup_minute)

        # If changing wakeup window
        elif preference_to_change == 3:
            print("Changing wakeup window.")
            new_wakeup_window = get_input("Please input new wakeup window (in minutes): ", "int", 0)

            change_wakeup_window(server_address, server_port, new_wakeup_window)

        # If changing UTC offset
        elif preference_to_change == 4:
            print("Changing UTC offset.")
            new_utc_offset = get_input("Please input new UTC offset: ", "int", 0)

            change_utc_offset(server_address, server_port, new_utc_offset)


def load_user_preferences(server_address, server_port):
    """
    Gets the user preferences as a dictionary from the server.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :return: user_preferences (dict)
    """
    # Connect to server
    connection = server_connection(server_address, server_port)

    # Request user preferences
    command = "get_user_preferences"
    connection.send(bytes(command, "utf-8"))

    # Receive and decode response
    msg = connection.recv(1024)
    user_preferences = msg.decode("utf-8")

    # Close connection
    connection.close()

    # Convert to dictionary
    user_preferences = ast.literal_eval(user_preferences)

    return user_preferences


def display_user_preferences(user_preferences):
    """
    Shows the current user preferences in a readable format.
    :param user_preferences: The current user preferences.
    :type user_preferences: dict
    :return: None
    """
    print("These are your current preferences stored on the server:")
    print("1.\tActive:\t\t", end="")
    if user_preferences["active_state"] == 1:
        print("Yes")
    else:
        print("No")
    print("2.\tWakeup time:\t", end="")
    if user_preferences["wakeup_time_hour"] < 10:
        print("0", end="")
    print(str(user_preferences["wakeup_time_hour"]) + ":", end="")
    if user_preferences["wakeup_time_minute"] < 10:
        print("0", end="")
    print(str(user_preferences["wakeup_time_minute"]))
    print("3.\tWakeup window:\t" + str(user_preferences["wakeup_window"]) + " minutes")
    if user_preferences["utc_offset"] > 0:
        utc_prefix = "+"
    else:
        utc_prefix = ""
    print("4.\tUTC offset:\t" + utc_prefix + str(user_preferences["utc_offset"]))


def change_active_state(server_address, server_port, current_active_state):
    """
    Changes the active state to whatever it wasn't before.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :param current_active_state: What the active state was before calling this function.
    :type current_active_state: int
    :return: None
    """
    if current_active_state == 0:
        set_active_state(server_address, server_port, 1)
    else:
        set_active_state(server_address, server_port, 0)


def set_active_state(server_address, server_port, new_active_state):
    """
    Sends a command to the server requesting the active state to be changed to the new_active_state parameter.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :param new_active_state: The new active state.
    :type new_active_state: int
    :return: None
    """
    # Connect to server
    connection = server_connection(server_address, server_port)

    # Request changing alarm state
    command = "set_active_state " + str(new_active_state)
    connection.send(bytes(command, "utf-8"))

    # Close connection
    connection.close()


def get_input(prompt, expected_type, speed):
    """
    Asks the user for input. Tests if its valid, and if not, ask again until a valid input has been entered.
    :param prompt: The text that should be used to ask for input.
    :type prompt: str
    :param expected_type: The expected type of the given value.
    :type expected_type: str
    :param speed: How much time the program shall wait before asking the user for a new value if the previous one
    was invalid.
    :type speed: int
    :return: user_input (any)
    """
    # Instantiate variables
    user_input = None
    user_input_ok = False

    # While user input is not in the correct format (default on first attempt)
    while not user_input_ok:
        # Prints the desired prompt, which usually describes what kind of information is requested
        print(prompt, end="")

        # Stores the input and checks if it's in the correct format
        user_input = input()
        is_ok, reason = is_clean_input(expected_type, user_input)

        if is_ok:
            # Breaks the loop
            user_input_ok = True
        else:
            # Asks for another attempt
            print(f"You did enter a correct value. Reason: {reason}.")
            if speed > 0:
                print(f"Please try again in {speed} seconds.")
            time.sleep(speed)

    # If the expected input type is an integer, make sure it converts from string (user input) to integer
    if expected_type == "int":
        user_input = int(user_input)

    return user_input


def is_clean_input(expected_type, value):
    """
    Tests if the given value is not empty and that it is of the expected type.
    :param expected_type: The expected type of the given value.
    :type: str
    :param value: The value to test.
    :type value: str
    :return: is_clean (bool), reason (str)
    """
    # Instantiate variables
    is_clean = False
    reason = ""

    # Checks if correct integer input
    if expected_type == "int":
        # If not empty
        if value != "":
            try:
                # If possible to convert to int
                int(value)
                is_clean = True

                # If not possible to convert to int
            except ValueError:
                is_clean = False
                reason = "ValueError"

        # If empty
        else:
            is_clean = False
            reason = "Empty"

    return is_clean, reason


def change_wakeup_time(server_address, server_port, hour_or_minute, value):
    """
    Changes the given type (hours or minute) to a given value.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :param hour_or_minute: Either 'hour' or 'minute'.
    :type hour_or_minute: str
    :param value: The new value for the given type.
    :type value: int
    :return: None
    """
    # Connect to server
    connection = server_connection(server_address, server_port)

    # Request changing alarm state
    command = "set_wakeup_" + hour_or_minute + " " + str(value)
    connection.send(bytes(command, "utf-8"))

    # Close connection
    connection.close()


def change_wakeup_window(server_address, server_port, new_wakeup_window):
    """
    Sends a command to the server requesting the wakeup window to be changed to the new_wakeup_window parameter.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :param new_wakeup_window: The new wakeup window in minutes.
    :type new_wakeup_window: int
    :return: None
    """
    # Connect to server
    connection = server_connection(server_address, server_port)

    # Request changing alarm state
    command = "set_wakeup_window " + str(new_wakeup_window)
    connection.send(bytes(command, "utf-8"))

    # Close connection
    connection.close()


def change_utc_offset(server_address, server_port, new_utc_offset):
    """
    Sends a command to the server requesting the UTC offset to be changed to the new_utc_offset parameter.
    :param server_address: The IP address of the server.
    :type server_address: str
    :param server_port: The port number of the server.
    :type server_port: str
    :param new_utc_offset: The new UTC offset in minutes.
    :type new_utc_offset: int
    :return: None
    """
    # Connect to server
    connection = server_connection(server_address, server_port)

    # Request changing alarm state
    command = "set_utc_offset " + str(new_utc_offset)
    connection.send(bytes(command, "utf-8"))

    # Close connection
    connection.close()


if __name__ == '__main__':
    main()
