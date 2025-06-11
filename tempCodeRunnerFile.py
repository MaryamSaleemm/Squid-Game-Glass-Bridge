def create_platform(self, pos, width, length):
        """
        Creates a solid cuboid platform model.
        The platform's top surface will be at pos.z.
        """
        format = GeomVertexFormat.getV3n3cpt2()
        vdata = GeomVertexData('platform', format, Geom.UHDynamic)
        vertex = GeomVertexWriter(vdata, 'vertex')
        normal = GeomVertexWriter(vdata, 'normal')
        color_writer = GeomVertexWriter(vdata, 'color')
        texcoord = GeomVertexWriter(vdata, 'texcoord')
        
        platform_color = VBase4(1.0, 0.0, 0.0, 1.0) # Solid platform color (Red)
        
        half_width, half_length, half_depth = width / 2, length / 2, self.tile_depth / 2 # Use tile_depth for platform thickness

        # Define vertices for a cuboid, with Z from -half_depth to half_depth (centered at 0)
        vertices = [
            # Front face (along -Y)
            (-half_width, -half_length, -half_depth), (half_width, -half_length, -half_depth), (half_width, -half_length, half_depth), (-half_width, -half_length, half_depth),
            # Back face (along +Y)
            (half_width, half_length, -half_depth), (-half_width, half_length, -half_depth), (-half_width, half_length, half_depth), (half_width, half_length, half_depth),
            # Right face (along +X)
            (half_width, -half_length, -half_depth), (half_width, half_length, -half_depth), (half_width, half_length, half_depth), (half_width, -half_length, half_depth),
            # Left face (along -X)
            (-half_width, half_length, -half_depth), (-half_width, -half_length, -half_depth), (-half_width, -half_length, half_depth), (-half_width, half_length, half_depth),
            # Top face (along +Z)
            (-half_width, -half_length, half_depth), (half_width, -half_length, half_depth), (half_width, half_length, half_depth), (-half_width, half_length, half_depth),
            # Bottom face (along -Z)
            (-half_width, half_length, -half_depth), (half_width, half_length, -half_depth), (half_width, -half_length, -half_depth), (-half_width, -half_length, -half_depth)
        ]
        
        normals = [
            (0,-1,0), (0,-1,0), (0,-1,0), (0,-1,0), # Front
            (0,1,0), (0,1,0), (0,1,0), (0,1,0),     # Back
            (1,0,0), (1,0,0), (1,0,0), (1,0,0),     # Right
            (-1,0,0), (-1,0,0), (-1,0,0), (-1,0,0), # Left
            (0,0,1), (0,0,1), (0,0,1), (0,0,1),     # Top
            (0,0,-1), (0,0,-1), (0,0,-1), (0,0,-1) # Bottom
        ]

        texcoords = [
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1)
        ]
        for i in range(len(vertices)):
            vertex.addData3f(*vertices[i])
            normal.addData3f(*normals[i])
            color_writer.addData4f(platform_color)
            texcoord.addData2f(*texcoords[i])

        tris = GeomTriangles(Geom.UHDynamic)
        indices = [
            0,1,2, 0,2,3,   # Front
            4,5,6, 4,6,7,   # Back
            8,9,10, 8,10,11, # Right
            12,13,14, 12,14,15, # Left
            16,17,18, 16,18,19, # Top
            20,21,22, 20,22,23  # Bottom
        ]
        for i in range(0, len(indices), 3):
            tris.addVertices(indices[i], indices[i+1], indices[i+2])
        
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode('platform_model')
        node.addGeom(geom)
        np = NodePath(node)
        # Adjust position so the top of the platform is at pos.z
        np.setPos(pos.getX(), pos.getY(), pos.getZ() + half_depth) 
        np.reparentTo(self.render)

        material = Material()
        material.setDiffuse(platform_color)
        material.setSpecular(VBase4(0.5, 0.5, 0.5, 1))
        material.setShininess(50.0)
        np.setMaterial(material)
        return np

    def setup_players(self):
        """
        Creates player objects and positions them on the starting platform.
        Initializes the active_players_queue.
        """
        player_colors = [
            VBase4(1.0, 0.8, 0.0, 1.0), # Yellow
            VBase4(0.0, 0.5, 1.0, 1.0), # Blue
            VBase4(0.5, 0.8, 0.2, 1.0), # Green
            VBase4(0.8, 0.2, 0.8, 1.0), # Purple
            VBase4(1.0, 0.5, 0.0, 1.0), # Orange
            VBase4(0.0, 0.8, 0.8, 1.0), # Cyan
            VBase4(0.8, 0.0, 0.8, 1.0)  # Magenta
        ]
        
        # Use selected_players from Tkinter
        player_names_for_game = self.selected_players_names if self.selected_players_names else [f"Player {i+1}" for i in range(self.num_players)]

        self.num_players = len(player_names_for_game) # Update num_players based on selection or default to 7

        player_start_y = self.bridge_start_y - (self.tile_width * 1.5)
        player_z_on_platform = self.tile_depth # Players stand on top of the platform

        # Calculate player starting positions to spread them out on the platform
        num_players_per_row = 4 # Max players per row on the starting platform
        player_spacing_x = self.tile_width / (num_players_per_row + 1)
        player_spacing_y = self.tile_width / 2

        for i, player_name in enumerate(player_names_for_game):
            row_idx = i // num_players_per_row
            col_idx = i % num_players_per_row
            
            x_offset = (col_idx - (num_players_per_row - 1) / 2) * player_spacing_x
            y_offset = row_idx * player_spacing_y 

            body_color = player_colors[i % len(player_colors)] # Cycle through the defined colors
            head_color = body_color 

            start_pos = LPoint3(x_offset, player_start_y + y_offset, player_z_on_platform)
            
            player = Player(player_name, start_pos, self, head_color=head_color, body_color=body_color)
            self.players.append(player)
            self.active_players_queue.append(player) # All players are active initially (added to deque)
            print(f"DEBUG (setup_players): Player {player.name} added to active_players_queue.")

    def display_player_status_ui(self):
        """
        Creates OnscreenText elements for each player's status.
        Adjusts Y offset for more players.
        """
        y_offset = 0.7 # Start Y for status text
        if self.num_players > 5:
            y_offset = 0.8 - (self.num_players * 0.03) 

        for player in self.players:
            text_node = OnscreenText(text=f"{player.name}: Ready", pos=(-1.2, y_offset), scale=0.04, fg=(1,1,1,1), align=TextNode.ALeft, mayChange=True)
            self.player_status_text[player.name] = text_node
            y_offset -= 0.05 # Smaller step for more players

    def update_player_info_display(self):
        """
        Updates the UI text showing the current player and instructions.
        """
        if self.current_player and not self.current_player.fallen and not self.current_player.crossed:
            self.player_info_text.setText(f"Current Player: {self.current_player.name}")
            self.instructions_text.setText("Press '1' for Left, '2' for Right")
        elif self.game_over_flag: # Check this flag to ensure game is truly over
            self.player_info_text.setText("Game Over!")
            self.instructions_text.setText("Press ESC to exit.")
        else: # Likely a transition state or all players finished but game_over hasn't been called yet
            self.player_info_text.setText("Waiting for next turn...")
            self.instructions_text.setText("")

    def highlight_current_player(self):
        """
        Highlights the current player and resets the highlight for others.
        """
        # Stop any existing pulse interval before resetting colors/scales
        if self.pulse_interval and self.pulse_interval.isPlaying():
            self.pulse_interval.finish()
            self.pulse_interval = None

        # Reset color and scale of all players to their original state
        for player in self.players:
            player.np.setColorScale(1, 1, 1, 1) # Reset color scale to normal (no tint)
            player.np.setScale(0.8) # Reset scale

        # Apply highlight to the current player
        if self.current_player and not self.current_player.fallen and not self.current_player.crossed:
            # Apply a yellowish tint for highlight
            self.current_player.np.setColorScale(1.5, 1.5, 0.5, 1) 
            # Simple pulse animation: grow from 0.8 to 0.9 and shrink back to 0.8
            self.pulse_interval = Sequence(
                self.current_player.np.scaleInterval(0.2, 0.9), # Grow slightly to 0.9
                self.current_player.np.scaleInterval(0.2, 0.8) # Shrink back to 0.8
            )
            self.pulse_interval.loop() # Use loop for continuous pulsing

    def attempt_move(self, chosen_col):
        """
        Handles player input for choosing a tile to move to.
        Only the current active player can make a choice.
        """
        if self.game_over_flag: # If game is over, ignore input
            print("DEBUG: Game is over. Ignoring input.")
            return

        if not self.current_player or not self.current_player.turn_active:
            print("DEBUG: Not current player's turn or no active player. Ignoring input.")
            self.game_status_text.setText("Not your turn or game ended!")
            return
        
        if self.current_player.fallen or self.current_player.crossed:
            print("DEBUG: Current player already finished. Ignoring input.")
            self.game_status_text.setText(f"{self.current_player.name} already finished!")
            return

        next_row = self.current_player.current_tile_row + 1

        if next_row >= self.bridge_length:
            print(f"DEBUG: {self.current_player.name} is at the end of the bridge or crossed. No more moves needed.")
            self.game_status_text.setText(f"{self.current_player.name} already at the end!")
            return

        # Check if the chosen tile exists and is valid
        if 0 <= next_row < self.bridge_length and 0 <= chosen_col < 2:
            # In Squid Game rules, we don't check if the tile is "occupied" by another player,
            # only if it's a valid tile to step on based on the game's rules.
            # The "observation" comes from knowing which tiles broke.
            
            print(f"DEBUG: {self.current_player.name} attempting to move to row {next_row}, col {chosen_col}")
            self.game_status_text.setText(f"{self.current_player.name}'s turn: Moving...")
            self.current_player.turn_active = False # Deactivate turn while move is in progress
            self.current_player.move_to_tile(next_row, chosen_col)
        else:
            print("Invalid move. Please choose '1' for Left or '2' for Right for the current tile.")
            self.game_status_text.setText("Invalid move! Try again.")
            self.current_player.turn_active = True # Keep turn active for invalid input

    def next_player_turn(self):
        """
        Advances the game to the next active player's turn for making a choice.
        This is called when the current player falls or crosses.
        """
        if self.game_over_flag:
            print("DEBUG (next_player_turn): Game is over. Not processing next turn.")
            return

        print(f"DEBUG (next_player_turn): Called. Current player before change: {self.current_player.name if self.current_player else 'None'}. Active queue size: {len(self.active_players_queue)}")

        # Ensure previous player's turn is properly ended and highlight removed
        if self.current_player:
            self.current_player.turn_active = False
            self.current_player.np.setColorScale(1, 1, 1, 1) # Reset color scale to normal
            self.current_player.np.setScale(0.8)

        # Remove the current player from the front of the deque if they have fallen or crossed
        if self.current_player and (self.active_players_queue and self.active_players_queue[0] == self.current_player): # Corrected: self.current_players_queue to self.active_players_queue
            removed_player = self.active_players_queue.popleft() # Remove from queue if finished
            print(f"DEBUG (next_player_turn): Removed {removed_player.name} from active queue.")

        # Re-evaluate active players for game over condition
        if not self.active_players_queue:
            self.game_over()
            return
        
        # Rotate the deque to make the next player the active one.
        if self.active_players_queue: 
            self.active_players_queue.rotate(-1) # Rotate left by one to move the next player to the front
            print(f"DEBUG (next_player_turn): Active queue rotated. New front: {self.active_players_queue[0].name}")
            
        if self.active_players_queue:
            self.current_player = self.active_players_queue[0] # Get the new current player
            self.current_player.turn_active = True
            self.current_player.current_tile_row = -1 # Reset current player to start of bridge
            self.current_player.current_tile_col = -1 # Reset current player to start of bridge
            self.current_player.is_on_bridge = False # Player starts on platform
            
            # Reset player's physical position to the starting platform
            # Find the original starting position from setup_players for the current player
            player_start_y = self.bridge_start_y - (self.tile_width * 1.5)
            player_z_on_platform = self.tile_depth
            num_players_per_row = 4 
            player_spacing_x = self.tile_width / (num_players_per_row + 1)
            player_spacing_y = self.tile_width / 2
            
            player_idx_in_all_players = self.players.index(self.current_player)
            row_idx = player_idx_in_all_players // num_players_per_row
            col_idx = player_idx_in_all_players % num_players_per_row
            x_offset = (col_idx - (num_players_per_row - 1) / 2) * player_spacing_x
            y_offset = row_idx * player_spacing_y 
            start_pos = LPoint3(x_offset, player_start_y + y_offset, player_z_on_platform)
            self.current_player.np.setPos(start_pos)


            self.camera_follow_player = self.current_player.np 
            self.update_player_info_display()
            self.highlight_current_player() # Highlight the new current player
            print(f"DEBUG: It's {self.current_player.name}'s turn to choose. Starting from the beginning.")
            self.game_status_text.setText(f"It's {self.current_player.name}'s turn! Start from Row 1.")
        else:
            self.game_over() # All players finished
            return

    def handle_time_up(self):
        """
        Called when the game timer runs out.
        All remaining active players are considered to have timed out.
        All unrevealed bridge tiles will fall.
        """
        if self.game_over_flag: # Prevent multiple calls to game_over
            return

        print("DEBUG: Time has run out! All remaining players are eliminated and bridge breaks.")
        self.game_status_text.setText("TIME OUT! Bridge breaks and players eliminated!")
        self.timer_active = False # Stop the timer

        # Mark all active players as fallen (timed out)
        players_timed_out = list(self.active_players_queue) # Create a copy to iterate
        for player in players_timed_out:
            if not player.fallen and not player.crossed:
                player.fallen = True
                player.is_on_bridge = False
                player.turn_active = False
                self.player_status_text[player.name].setText(f"{player.name}: Timed Out!")
                if player.np: # Detach their model if it's still there
                    player.np.detachNode()
        
        self.active_players_queue.clear() # Clear the queue as all are out

        # Make all unrevealed bridge tiles fall
        for r_idx, row_tiles in enumerate(self.bridge_tiles):
            for c_idx, tile_info in enumerate(row_tiles):
                # Check if this tile has NOT been revealed as safe or broken yet
                if r_idx not in self.revealed_safe_path and r_idx not in self.revealed_broken_path:
                    # Animate the tile falling
                    fall_tile_interval = tile_info['np'].posInterval(0.5, LPoint3(tile_info['x'], tile_info['y'], -5),
                                                                     startPos=tile_info['np'].getPos())
                    # Also make it look broken/darker and transparent as it falls
                    tile_info['np'].setTransparency(TransparencyAttrib.M_alpha)
                    tile_info['np'].setColor(Vec4(0.2, 0.2, 0.2, 0.3)) 
                    fall_tile_interval.start()
                elif r_idx in self.revealed_safe_path and self.revealed_safe_path[r_idx] != c_idx:
                    # If the other tile in this row was safe, but this one wasn't revealed, it must be the broken one
                    # This handles cases where a player stepped on the safe one, leaving the other unrevealed.
                    fall_tile_interval = tile_info['np'].posInterval(0.5, LPoint3(tile_info['x'], tile_info['y'], -5),
                                                                     startPos=tile_info['np'].getPos())
                    tile_info['np'].setTransparency(TransparencyAttrib.M_alpha)
                    tile_info['np'].setColor(Vec4(0.2, 0.2, 0.2, 0.3)) 
                    fall_tile_interval.start()


        self.game_over(time_limit_reached_flag=True) # Call game over to finalize state, indicating time limit was reached

    def game_over(self, time_limit_reached_flag=False):
        """
        Ends the game, displays results, and disables further input.
        Also updates the database with final game results.
        """
        if self.game_over_flag:
            return # Already handled game over

        print("DEBUG: All players have finished their attempt (either fallen or crossed). Game Over!")
        self.game_over_flag = True
        self.timer_active = False # Ensure timer stops

        self.game_status_text.setText("Game Over!")
        winners = [player.name for player in self.players if player.crossed]
        if winners:
            self.player_info_text.setText(f"Winners: {', '.join(winners)}")
        else:
            self.player_info_text.setText("No one crossed the bridge.")
        self.instructions_text.setText("Press ESC to exit.")
        self.ignore_all() # Ignore all previous inputs
        self.accept("escape", self.userExit) # Re-enable ESC to exit
        self.current_player = None # Clear current player as game is over
        self.camera_follow_player = None # Stop camera following a specific player

        # --- Save final game results to database ---
        self._update_game_session_results(time_limit_reached_flag)
        if self.conn:
            try:
                self.conn.close() # Close the database connection
                print("DEBUG: Database connection closed.")
            except MySQLConnectionError as e:
                print(f"ERROR: Failed to close database connection: {e}")
            except Exception as e:
                print(f"ERROR: An unexpected error occurred while closing database connection: {e}")


    def update_game_state(self, task):
        """
        Main game loop task to check for game over condition and manage turn progression.
        """
        if self.game_over_flag:
            return task.done # Stop this task if game is over

        # If no active players left, game is over.
        if not self.active_players_queue and not self.game_over_flag: # Added game_over_flag check
            self.game_over()
            return task.done
        
        # This task loop mainly ensures that if a player somehow becomes inactive without
        # next_player_turn being called, it will be triggered.
        if self.current_player is None or (self.current_player.fallen or self.current_player.crossed):
            self.next_player_turn()
        # If the current player is active and waiting for input, do nothing in this task loop.
        # Their turn will progress via attempt_move -> check_tile.
        elif self.current_player and self.current_player.turn_active:
            pass # Current player is active, waiting for input.

        return task.cont

    def update_timer(self, task):
        """
        Updates the global game timer.
        """
        if self.game_over_flag:
            self.timer_text.setText(f"Time Left: 0") # Ensure timer shows 0 at end
            return task.done # Stop the timer task

        if self.timer_active:
            self.time_left -= globalClock.getDt() # type: ignore
            if self.time_left <= 0:
                self.time_left = 0
                self.timer_text.setText(f"Time Left: 0")
                self.handle_time_up()
                return task.done # Stop the timer task

            self.timer_text.setText(f"Time Left: {self.time_left:.0f}") # Display as whole seconds
        
        return task.cont

    def update_camera(self, task):
        """
        Smoothly moves the camera to follow the current lead player.
        """
        target_follow_node = None
        
        # Always follow the current player if they are active
        if self.current_player and not self.current_player.fallen and not self.current_player.crossed:
            target_follow_node = self.current_player.np
        
        self.camera_follow_player = target_follow_node # Update the camera_follow_player reference

        if self.camera_follow_player:
            # Adjust camera position relative to the target player
            target_pos = self.camera_follow_player.getPos() + LVector3(0, -15, 10) 
            current_pos = self.camera.getPos()
            
            # Smooth interpolation for camera movement
            new_pos = current_pos + (target_pos - current_pos) * 0.05
            self.camera.setPos(new_pos)
            self.camera.lookAt(self.camera_follow_player.getPos() + LVector3(0, 0, 0.5)) 
        return task.cont


# --- Main Tkinter Application Setup ---
if __name__ == '__main__':
    root = Tk()
    root.title("Squid Game - Glass Bridge")
    root.state('zoomed') # Maximize the window
    root.resizable(True, True)

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # Global variables to store selected players/staff from Tkinter
    selected_players = []
    selected_staff = []

    show_welcome_screen() # Call this to start the application
    root.mainloop()
