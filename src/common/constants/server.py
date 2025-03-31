class RasptankMessageFactory:
    """Factory class to build MQTT messages and topics for Rasptank interaction with the server."""

    def __init__(self, tank_id: str):
        self.tank_id = tank_id

    # --- Topic Generators --- #
    def init_topic(self):
        return f"tanks/{self.tank_id}/init"

    def flag_topic(self):
        return f"tanks/{self.tank_id}/flag"

    def shots_topic(self):
        return f"tanks/{self.tank_id}/shots"

    def shot_in_topic(self):
        return f"tanks/{self.tank_id}/shots/in"

    def shot_out_topic(self):
        return f"tanks/{self.tank_id}/shots/out"

    def qr_topic(self):
        return f"tanks/{self.tank_id}/qr_code"

    # --- Message Generators --- #
    @staticmethod
    def init_request(tank_id: str):
        return "init", f"INIT {tank_id}"

    def team_assignment(self, team_color: str):
        return self.init_topic(), f"TEAM {team_color.upper()}"

    def qr_code_assignment(self, qr_code: str):
        return self.init_topic(), f"QR_CODE {qr_code}"

    def enter_flag_area(self):
        return self.flag_topic(), "ENTER_FLAG_AREA"

    def exit_flag_area(self):
        return self.flag_topic(), "EXIT_FLAG_AREA"

    def start_catching(self):
        return self.flag_topic(), "START_CATCHING"

    def flag_catched(self):
        return self.flag_topic(), "FLAG_CATCHED"

    def abort_catching_exit(self):
        return self.flag_topic(), "ABORT_CATCHING_EXIT"

    def shot_by(self, shooter_id: str):
        return self.shots_topic(), f"SHOT_BY {shooter_id}"

    def shot_notification(self, direction: str):
        if direction == "in":
            return self.shot_in_topic(), "SHOT"
        elif direction == "out":
            return self.shot_out_topic(), "SHOT"
        raise ValueError("Invalid direction for shot notification. Use 'in' or 'out'.")

    def flag_lost(self):
        return self.flag_topic(), "FLAG_LOST"

    def qr_code_scan(self, qr_code: str):
        return self.qr_topic(), f"QR_CODE {qr_code}"

    def scan_successful(self):
        return self.qr_topic(), "SCAN_SUCCESSFUL"

    def flag_deposited(self):
        return self.qr_topic(), "FLAG_DEPOSITED"

    def win_notification(self, winning_team: str):
        return self.flag_topic(), f"WIN {winning_team.upper()}"
