import socket
import time
import re
from dataclasses import dataclass
from typing import Optional

# ============================================================================
#                               CONFIG & SETTINGS
# ============================================================================
class Config:
    class Hardware:
        PIN_ESC_M1 = 2   # Arka Sol Motor
        PIN_ESC_M2 = 3   # Arka Sağ Motor
        PIN_ESC_M3 = 4   # Ön Sol Motor
        PIN_ESC_M4 = 5   # Ön Sağ Motor
        PIN_ESC_M5 = 6   # Sol Dikey Motor
        PIN_ESC_M6 = 7   # Sağ Dikey Motor
        THRUSTER_COUNT = 6

    class MotorDirection:
        INVERT_M1 = -1    # M1 Arka Sol
        INVERT_M2 = -1    # M2 Arka Sağ
        INVERT_M3 = 1    # M3 Ön Sol
        INVERT_M4 = 1    # M4 Ön Sağ
        INVERT_M5 = -1    # M5 Sol Dikey
        INVERT_M6 = -1    # M6 Sağ Dikey

    class Network:
        IP_ADDRESS = "127.0.0.1"
        LOCAL_PORT = 5032
        BUFFER_SIZE = 64

    class ESC:
        PWM_MIN = 1000
        PWM_NEUTRAL = 1500
        PWM_MAX = 2000
        INIT_DELAY_SEC = 2.0

    class Motor:
        PERCENT_MIN = -100
        PERCENT_MAX = 100
        DEADZONE = 5

    class Debug:
        ENABLE_DEBUG = True
        PRINT_PACKETS = True
        PRINT_PARSED = True
        PRINT_PWM = True


# ============================================================================
# UTILITIES MODULE
# ============================================================================
class Utilities:
    @staticmethod
    def clamp(value: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(value, max_val))

    @staticmethod
    def apply_deadzone(value: int, deadzone: int) -> int:
        if -deadzone <= value <= deadzone:
            return 0
        return value

    @staticmethod
    def map_percent_to_pwm(percentage: int, min_percent: int, max_percent: int, pwm_min: int, pwm_max: int) -> int:
        clamped_percent = Utilities.clamp(percentage, min_percent, max_percent)
        denominator = max_percent - min_percent
        
        if denominator == 0:
            return Config.ESC.PWM_NEUTRAL
            
        numerator = (clamped_percent - min_percent) * (pwm_max - pwm_min)
        result = pwm_min + (numerator / denominator)
        return int(Utilities.clamp(result, pwm_min, pwm_max))


# ============================================================================
# DATA STRUCTURES
# ============================================================================
@dataclass
class MotorOutputs:
    m1: int = 0  # Arka Sol
    m2: int = 0  # Arka Sağ
    m3: int = 0  # Ön Sol
    m4: int = 0  # Ön Sağ
    m5: int = 0  # Sol Dikey
    m6: int = 0  # Sağ Dikey

@dataclass
class ControlCommands:
    forward: int = 0
    strafe: int = 0
    yaw: int = 0
    vertical: int = 0
    emergency_stop: bool = False
    is_valid: bool = False


# ============================================================================
# ESC CONTROLLER CLASS
# ============================================================================
class ESCController:
    def __init__(self):
        self.current_pwm = [Config.ESC.PWM_NEUTRAL] * Config.Hardware.THRUSTER_COUNT

    def begin(self):
        if Config.Debug.ENABLE_DEBUG:
            print("[ESC] Initializing ESCs to NEUTRAL...")
        self.stop_all()
        time.sleep(Config.ESC.INIT_DELAY_SEC)

    def set_motor_percent(self, motor_index: int, percentage: int):
        if motor_index < 0 or motor_index >= Config.Hardware.THRUSTER_COUNT:
            return

        pwm_value = Utilities.map_percent_to_pwm(
            percentage,
            Config.Motor.PERCENT_MIN,
            Config.Motor.PERCENT_MAX,
            Config.ESC.PWM_MIN,
            Config.ESC.PWM_MAX
        )

        self.current_pwm[motor_index] = pwm_value
        
        # Donanım sürücüsü entegrasyonu (örn. pigpio) buraya eklenebilir.
        
        if Config.Debug.ENABLE_DEBUG and Config.Debug.PRINT_PWM:
            print(f"M{motor_index + 1} PWM: {pwm_value}")

    def stop_all(self):
        for i in range(Config.Hardware.THRUSTER_COUNT):
            self.current_pwm[i] = Config.ESC.PWM_NEUTRAL
            # Donanım çıkışı nötrlenir.


# ============================================================================
# MOTION CONTROLLER CLASS
# ============================================================================
class MotionController:
    def calculate_outputs(self, f: int, s: int, y: int, v: int) -> MotorOutputs:
        forward = Utilities.apply_deadzone(f, Config.Motor.DEADZONE)
        strafe  = Utilities.apply_deadzone(s, Config.Motor.DEADZONE)
        yaw     = Utilities.apply_deadzone(y, Config.Motor.DEADZONE)
        vert    = Utilities.apply_deadzone(v, Config.Motor.DEADZONE)

        outputs = MotorOutputs()

        # Dikey Eksen (M5 ve M6)
        outputs.m5 = vert
        outputs.m6 = vert

        # İleri/Geri Eksen (M1 ve M2)
        outputs.m1 = forward
        outputs.m2 = forward

        # Dönüş / Yaw Ekseni (M3 ve M4)
        if yaw > 0:
            outputs.m3 = yaw
            outputs.m4 = 0
        elif yaw < 0:
            outputs.m3 = 0
            outputs.m4 = -yaw
        else:
            outputs.m3 = 0
            outputs.m4 = 0

        # Yanal Kayma / Strafe Mantığı (Sadece robot dururken)
        if strafe != 0 and forward == 0 and yaw == 0:
            outputs.m1 = strafe
            outputs.m3 = strafe
            outputs.m2 = -strafe
            outputs.m4 = -strafe

        # Yazılımsal Invert (Yön Çevirme)
        outputs.m1 *= Config.MotorDirection.INVERT_M1
        outputs.m2 *= Config.MotorDirection.INVERT_M2
        outputs.m3 *= Config.MotorDirection.INVERT_M3
        outputs.m4 *= Config.MotorDirection.INVERT_M4
        outputs.m5 *= Config.MotorDirection.INVERT_M5
        outputs.m6 *= Config.MotorDirection.INVERT_M6

        # Sınırlandırma (-100 ile %100 arası)
        outputs.m1 = int(Utilities.clamp(outputs.m1, Config.Motor.PERCENT_MIN, Config.Motor.PERCENT_MAX))
        outputs.m2 = int(Utilities.clamp(outputs.m2, Config.Motor.PERCENT_MIN, Config.Motor.PERCENT_MAX))
        outputs.m3 = int(Utilities.clamp(outputs.m3, Config.Motor.PERCENT_MIN, Config.Motor.PERCENT_MAX))
        outputs.m4 = int(Utilities.clamp(outputs.m4, Config.Motor.PERCENT_MIN, Config.Motor.PERCENT_MAX))
        outputs.m5 = int(Utilities.clamp(outputs.m5, Config.Motor.PERCENT_MIN, Config.Motor.PERCENT_MAX))
        outputs.m6 = int(Utilities.clamp(outputs.m6, Config.Motor.PERCENT_MIN, Config.Motor.PERCENT_MAX))

        return outputs


# ============================================================================
# PACKET PARSER CLASS
# ============================================================================
class PacketParser:
    def parse_packet(self, buffer_str: str) -> ControlCommands:
        cmds = ControlCommands()

        if not buffer_str:
            return cmds

        # Acil Durdurma Kontrolü
        if "STOP" in buffer_str or "EMERGENCY" in buffer_str:
            cmds.emergency_stop = True
            cmds.is_valid = True
            return cmds

        cmds.forward  = self._extract_value(buffer_str, 'F')
        cmds.strafe   = self._extract_value(buffer_str, 'S')
        cmds.vertical = self._extract_value(buffer_str, 'V')
        cmds.yaw      = self._extract_value(buffer_str, 'Y')
        cmds.is_valid = True

        if Config.Debug.ENABLE_DEBUG and Config.Debug.PRINT_PARSED:
            print(f"Parsed -> F: {cmds.forward} | S: {cmds.strafe} | V: {cmds.vertical} | Y: {cmds.yaw}")

        return cmds

    def _extract_value(self, buffer_str: str, key: str) -> int:
        # Regex ile key kelimesinden sonra gelen sayısal değeri bulur (Örn: F:50, F=50, F 50)
        pattern = rf"{key}[:=\s]*(-?\d+)"
        match = re.search(pattern, buffer_str)
        if match:
            val = int(match.group(1))
            return int(Utilities.clamp(val, Config.Motor.PERCENT_MIN, Config.Motor.PERCENT_MAX))
        return 0


# ============================================================================
# ETHERNET/UDP RECEIVER CLASS
# ============================================================================
class EthernetReceiver:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Sockets zaman aşımını non-blocking / kısa süreli yapmak için:
        self.sock.settimeout(0.1)

    def begin(self):
        self.sock.bind((Config.Network.IP_ADDRESS, Config.Network.LOCAL_PORT))
        if Config.Debug.ENABLE_DEBUG:
            print(f"UDP Listening on {Config.Network.IP_ADDRESS}:{Config.Network.LOCAL_PORT}")

    def read_packet(self) -> tuple[Optional[str], int]:
        try:
            data, _ = self.sock.recvfrom(Config.Network.BUFFER_SIZE)
            buffer_str = data.decode('utf-8', errors='ignore').strip()
            
            if Config.Debug.ENABLE_DEBUG and Config.Debug.PRINT_PACKETS:
                print(f"Rx Packet [{len(data)} bytes]: {buffer_str}")
                
            return buffer_str, len(data)
        except socket.timeout:
            return None, 0
        except Exception as e:
            if Config.Debug.ENABLE_DEBUG:
                print(f"Socket Error: {e}")
            return None, 0


# ============================================================================
# MAIN PROGRAM LOOP
# ============================================================================
def main():
    esc_controller = ESCController()
    motion_controller = MotionController()
    packet_parser = PacketParser()
    ethernet_receiver = EthernetReceiver()

    WATCHDOG_TIMEOUT_SEC = 1.0  # 1 Saniye sinyal gelmezse motorları durdur

    if Config.Debug.ENABLE_DEBUG:
        print("========================================")
        print(" ROV Competition Firmware Initializing ")
        print("========================================")

    esc_controller.begin()
    ethernet_receiver.begin()

    last_packet_time = time.time()

    if Config.Debug.ENABLE_DEBUG:
        print("ROV System Online and Ready. Waiting for commands...")

    try:
        while True:
            packet_str, bytes_read = ethernet_receiver.read_packet()

            if bytes_read > 0 and packet_str:
                last_packet_time = time.time()
                cmds = packet_parser.parse_packet(packet_str)

                if cmds.is_valid:
                    if cmds.emergency_stop:
                        esc_controller.stop_all()
                        if Config.Debug.ENABLE_DEBUG:
                            print("!!! EMERGENCY STOP TRIGGERED !!!")
                    else:
                        outputs = motion_controller.calculate_outputs(
                            cmds.forward,
                            cmds.strafe,
                            cmds.yaw,
                            cmds.vertical
                        )

                        esc_controller.set_motor_percent(0, outputs.m1)
                        esc_controller.set_motor_percent(1, outputs.m2)
                        esc_controller.set_motor_percent(2, outputs.m3)
                        esc_controller.set_motor_percent(3, outputs.m4)
                        esc_controller.set_motor_percent(4, outputs.m5)
                        esc_controller.set_motor_percent(5, outputs.m6)

            # Fail-Safe Watchdog (Bağlantı koparsa güvenli duruş)
            if time.time() - last_packet_time > WATCHDOG_TIMEOUT_SEC:
                esc_controller.stop_all()

            # CPU aşırı kullanımını önlemek için küçük bir bekleme
            time.sleep(0.005)

    except KeyboardInterrupt:
        print("\nStopping ROV System...")
        esc_controller.stop_all()

if __name__ == "__main__":
    main()