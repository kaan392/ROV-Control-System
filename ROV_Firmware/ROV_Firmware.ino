/**
   @file ROV_Firmware.ino
   @brief Refactored & Bug-Fixed Underwater ROV Firmware.
*/

#include <Arduino.h>
#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <Servo.h>
#include <stdlib.h>
#include <string.h>

namespace Config {

namespace Hardware {
constexpr uint8_t PIN_ESC_M1 = 2; // Arka Sol Motor
constexpr uint8_t PIN_ESC_M2 = 3; // Arka Sağ Motor
constexpr uint8_t PIN_ESC_M3 = 5; // Ön Sol Motor
constexpr uint8_t PIN_ESC_M4 = 6; // Ön Sağ Motor
constexpr uint8_t PIN_ESC_M5 = 7; // Sol Dikey Motor
constexpr uint8_t PIN_ESC_M6 = 8; // Sağ Dikey Motor
constexpr uint8_t THRUSTER_COUNT = 6;
}

namespace MotorDirection {
constexpr int8_t INVERT_M1 = -1; 
constexpr int8_t INVERT_M2 = -1; 
constexpr int8_t INVERT_M3 =  1; 
constexpr int8_t INVERT_M4 =  1; 
constexpr int8_t INVERT_M5 = -1; 
constexpr int8_t INVERT_M6 = -1; 
}

namespace Network {
constexpr uint8_t MAC_ADDRESS[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };
constexpr uint8_t IP_ADDRESS[]  = { 127,0,0,1 };
constexpr uint8_t GATEWAY[]     = { 192, 168, 1, 1 };
constexpr uint8_t SUBNET[]      = { 255, 255, 255, 0 };
constexpr uint8_t DNS_SERVER[]  = { 192, 168, 1, 1 };

constexpr uint16_t LOCAL_PORT   = 5032;
constexpr uint8_t BUFFER_SIZE   = 64;
}

namespace ESC {
constexpr uint16_t PWM_MIN     = 1000;
constexpr uint16_t PWM_NEUTRAL = 1500;
constexpr uint16_t PWM_MAX     = 2000;

constexpr uint32_t INIT_DELAY_MS = 2000; 
}

namespace Motor {
constexpr int8_t PERCENT_MIN = -100;
constexpr int8_t PERCENT_MAX = 100;
constexpr int8_t DEADZONE    = 2;
}

namespace Debug {
constexpr bool ENABLE_DEBUG       = true;
constexpr unsigned long BAUDRATE  = 115200;
constexpr bool PRINT_PACKETS      = true;
constexpr bool PRINT_PARSED       = true;
constexpr bool PRINT_PWM          = false;
}

} // namespace Config

namespace Utilities {

template <typename T>
inline T clamp(T value, T minVal, T maxVal) {
  if (value < minVal) return minVal;
  if (value > maxVal) return maxVal;
  return value;
}

inline int8_t applyDeadzone(int8_t value, int8_t deadzone) {
  if (value >= -deadzone && value <= deadzone) {
    return 0;
  }
  return value;
}

inline uint16_t mapPercentToPWM(int8_t percentage, int8_t minPercent, int8_t maxPercent, uint16_t pwmMin, uint16_t pwmMax) {
  int8_t clampedPercent = clamp(percentage, minPercent, maxPercent);
  long numerator = (long)(clampedPercent - minPercent) * (long)(pwmMax - pwmMin);
  long denominator = (long)(maxPercent - minPercent);

  if (denominator == 0) return Config::ESC::PWM_NEUTRAL;

  long result = pwmMin + (numerator / denominator);
  return (uint16_t)clamp(result, (long)pwmMin, (long)pwmMax);
}
}

struct MotorOutputs {
  int8_t m1; 
  int8_t m2; 
  int8_t m3; 
  int8_t m4; 
  int8_t m5; 
  int8_t m6; 
};

struct ControlCommands {
  int8_t forward;
  int8_t strafe;
  int8_t yaw;
  int8_t vertical;
  bool emergencyStop;
  bool isValid;
};

class ESCController {
  public:
    ESCController() {
      for (uint8_t i = 0; i < Config::Hardware::THRUSTER_COUNT; ++i) {
        m_currentPWM[i] = Config::ESC::PWM_NEUTRAL;
      }
    }

    void begin() {
      const uint8_t pins[Config::Hardware::THRUSTER_COUNT] = {
        Config::Hardware::PIN_ESC_M1, Config::Hardware::PIN_ESC_M2,
        Config::Hardware::PIN_ESC_M3, Config::Hardware::PIN_ESC_M4,
        Config::Hardware::PIN_ESC_M5, Config::Hardware::PIN_ESC_M6
      };

      for (uint8_t i = 0; i < Config::Hardware::THRUSTER_COUNT; ++i) {
        m_escs[i].attach(pins[i], Config::ESC::PWM_MIN, Config::ESC::PWM_MAX);
        m_escs[i].writeMicroseconds(Config::ESC::PWM_NEUTRAL);
      }

      delay(Config::ESC::INIT_DELAY_MS);
    }

    void setMotorPercent(uint8_t motorIndex, int8_t percentage) {
      if (motorIndex >= Config::Hardware::THRUSTER_COUNT) return;

      uint16_t pwmValue = Utilities::mapPercentToPWM(
                            percentage,
                            Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX,
                            Config::ESC::PWM_MIN, Config::ESC::PWM_MAX
                          );

      m_currentPWM[motorIndex] = pwmValue;
      m_escs[motorIndex].writeMicroseconds(pwmValue);
    }

    void stopAll() {
      for (uint8_t i = 0; i < Config::Hardware::THRUSTER_COUNT; ++i) {
        m_currentPWM[i] = Config::ESC::PWM_NEUTRAL;
        m_escs[i].writeMicroseconds(Config::ESC::PWM_NEUTRAL);
      }
    }

  private:
    Servo m_escs[Config::Hardware::THRUSTER_COUNT];
    uint16_t m_currentPWM[Config::Hardware::THRUSTER_COUNT];
};

class MotionController {
  public:
    MotionController() {}

    MotorOutputs calculateOutputs(int8_t f, int8_t s, int8_t y, int8_t v) {
      int8_t forward = Utilities::applyDeadzone(f, Config::Motor::DEADZONE);
      int8_t strafe  = Utilities::applyDeadzone(s, Config::Motor::DEADZONE);
      int8_t yaw      = Utilities::applyDeadzone(y, Config::Motor::DEADZONE);
      int8_t vert     = Utilities::applyDeadzone(v, Config::Motor::DEADZONE);

      MotorOutputs outputs = {0, 0, 0, 0, 0, 0};

      // Dikey Eksen (M5 ve M6)
      outputs.m5 = vert;
      outputs.m6 = vert;

      // İleri/Geri ve Dönüş (Diferansiyel Miksaj)
      if (strafe == 0) {
        outputs.m1 = forward - yaw;
        outputs.m2 = forward + yaw;
        outputs.m3 = forward + yaw;
        outputs.m4 = forward - yaw;
      } else if (forward == 0 && yaw == 0) {
        // Yanal Kayma / Strafe
        outputs.m1 = -strafe;
        outputs.m2 = strafe;
        outputs.m3 = strafe;
        outputs.m4 = -strafe;
      }

      // Yazılımsal Invert
      outputs.m1 *= Config::MotorDirection::INVERT_M1;
      outputs.m2 *= Config::MotorDirection::INVERT_M2;
      outputs.m3 *= Config::MotorDirection::INVERT_M3;
      outputs.m4 *= Config::MotorDirection::INVERT_M4;
      outputs.m5 *= Config::MotorDirection::INVERT_M5;
      outputs.m6 *= Config::MotorDirection::INVERT_M6;

      // Sınırlandırma (%-100 ile %100 arası)
      outputs.m1 = Utilities::clamp(outputs.m1, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m2 = Utilities::clamp(outputs.m2, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m3 = Utilities::clamp(outputs.m3, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m4 = Utilities::clamp(outputs.m4, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m5 = Utilities::clamp(outputs.m5, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m6 = Utilities::clamp(outputs.m6, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);

      return outputs;
    }
};

class PacketParser {
  public:
    PacketParser() {}

    ControlCommands parsePacket(const char* buffer, uint16_t length) {
      ControlCommands cmds = {0, 0, 0, 0, false, false};

      if (buffer == nullptr || length == 0) return cmds;

      if (strstr(buffer, "STOP") != nullptr || strstr(buffer, "EMERGENCY") != nullptr) {
        cmds.emergencyStop = true;
        cmds.isValid = true;
        return cmds;
      }

      int f = 0, s = 0, y = 0, v = 0, e = 0;
      // Python ControlPacket formatına tam uyumlu sscanf ayrıştırma
      if (sscanf(buffer, "F:%d,S:%d,Y:%d,V:%d,E:%d", &f, &s, &y, &v, &e) >= 4) {
        cmds.forward  = Utilities::clamp((int8_t)f, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
        cmds.strafe   = Utilities::clamp((int8_t)s, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
        cmds.yaw      = Utilities::clamp((int8_t)y, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
        cmds.vertical = Utilities::clamp((int8_t)v, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
        cmds.emergencyStop = (e > 0);
        cmds.isValid  = true;
      }

      return cmds;
    }
};

class EthernetReceiver {
  public:
    EthernetReceiver()
      : m_ip(Config::Network::IP_ADDRESS[0], Config::Network::IP_ADDRESS[1],
             Config::Network::IP_ADDRESS[2], Config::Network::IP_ADDRESS[3]) {}

    void begin() {
      Ethernet.init(10); // W5500 / W5100 CS pini

      IPAddress dns(Config::Network::DNS_SERVER[0], Config::Network::DNS_SERVER[1], Config::Network::DNS_SERVER[2], Config::Network::DNS_SERVER[3]);
      IPAddress gateway(Config::Network::GATEWAY[0], Config::Network::GATEWAY[1], Config::Network::GATEWAY[2], Config::Network::GATEWAY[3]);
      IPAddress subnet(Config::Network::SUBNET[0], Config::Network::SUBNET[1], Config::Network::SUBNET[2], Config::Network::SUBNET[3]);

      Ethernet.begin((uint8_t*)Config::Network::MAC_ADDRESS, m_ip, dns, gateway, subnet);
      m_udp.begin(Config::Network::LOCAL_PORT);
    }

    uint16_t readPacket(char* outputBuffer, uint16_t maxLen) {
      int packetSize = m_udp.parsePacket();
      if (packetSize <= 0) return 0;

      int len = m_udp.read(outputBuffer, maxLen - 1);
      if (len > 0) {
        outputBuffer[len] = '\0';
      }

      return (uint16_t)len;
    }

  private:
    EthernetUDP m_udp;
    IPAddress m_ip;
};

ESCController     escController;
MotionController   motionController;
PacketParser       packetParser;
EthernetReceiver   ethernetReceiver;

char packetBuffer[Config::Network::BUFFER_SIZE];
unsigned long lastPacketTime = 0;
constexpr unsigned long WATCHDOG_TIMEOUT_MS = 1000;

void setup() {
  if (Config::Debug::ENABLE_DEBUG) {
    Serial.begin(Config::Debug::BAUDRATE);
    while (!Serial && millis() < 3000);
  }

  escController.begin();
  ethernetReceiver.begin();

  lastPacketTime = millis();
}

void loop() {
  uint16_t bytesRead = ethernetReceiver.readPacket(packetBuffer, Config::Network::BUFFER_SIZE);

  if (bytesRead > 0) {
    lastPacketTime = millis();

    ControlCommands cmds = packetParser.parsePacket(packetBuffer, bytesRead);

    if (cmds.isValid) {
      if (cmds.emergencyStop) {
        escController.stopAll();
      } else {
        MotorOutputs outputs = motionController.calculateOutputs(
                                 cmds.forward,
                                 cmds.strafe,
                                 cmds.yaw,
                                 cmds.vertical
                               );

        escController.setMotorPercent(0, outputs.m1);
        escController.setMotorPercent(1, outputs.m2);
        escController.setMotorPercent(2, outputs.m3);
        escController.setMotorPercent(3, outputs.m4);
        escController.setMotorPercent(4, outputs.m5);
        escController.setMotorPercent(5, outputs.m6);
      }
    }
  }

  // Fail-Safe Watchdog
  if (millis() - lastPacketTime > WATCHDOG_TIMEOUT_MS) {
    escController.stopAll();
  }
}
