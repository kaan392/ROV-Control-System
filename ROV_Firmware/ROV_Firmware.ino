/**
   @file ROV_Firmware.ino
   @brief Complete Single-File Implementation of Underwater ROV Firmware.
*/

#include <Arduino.h>
#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <Servo.h>
#include <stdlib.h>
#include <string.h>

// ============================================================================
//                       CONFIG & SYSTEM SETTINGS
// ============================================================================
namespace Config {

// ------------------------------------------------------------------------
// 1. HARDWARE / ESC PINS (Arduino Mega 2560 PWM Pins)
// ------------------------------------------------------------------------
namespace Hardware {
constexpr uint8_t PIN_ESC_M1 = 2; // Arka Sol Motor
constexpr uint8_t PIN_ESC_M2 = 3; // Arka Sağ Motor
constexpr uint8_t PIN_ESC_M3 = 4; // Ön Sol Motor
constexpr uint8_t PIN_ESC_M4 = 5; // Ön Sağ Motor
constexpr uint8_t PIN_ESC_M5 = 6; // Sol Dikey Motor
constexpr uint8_t PIN_ESC_M6 = 7; // Sağ Dikey Motor
constexpr uint8_t THRUSTER_COUNT = 6;
}

// ------------------------------------------------------------------------
// 2. MOTOR DIRECTION INVERSION (-1: Ters Yön, 1: Normal Yön)
// ------------------------------------------------------------------------
namespace MotorDirection {
constexpr int8_t INVERT_M1 =  -1; // M1 Arka Sol
constexpr int8_t INVERT_M2 =  -1; // M2 Arka Sağ
constexpr int8_t INVERT_M3 =  1; // M3 Ön Sol
constexpr int8_t INVERT_M4 =  1; // M4 Ön Sağ
constexpr int8_t INVERT_M5 =  -1; // M5 Sol Dikey
constexpr int8_t INVERT_M6 =  -1; // M6 Sağ Dikey
}

// ------------------------------------------------------------------------
// 3. NETWORK CONFIGURATION (W5500 Ethernet Modülü)
// ------------------------------------------------------------------------
namespace Network {
constexpr uint8_t MAC_ADDRESS[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };
constexpr uint8_t IP_ADDRESS[]  = { 127,0,0,1 };
constexpr uint8_t GATEWAY[]     = { 192, 168, 1, 1 };
constexpr uint8_t SUBNET[]      = { 255, 255, 255, 0 };

constexpr uint16_t LOCAL_PORT   = 5032;
constexpr uint8_t BUFFER_SIZE   = 32;
}

// ------------------------------------------------------------------------
// 4. ESC PWM LIMITS
// ------------------------------------------------------------------------
namespace ESC {
constexpr uint16_t PWM_MIN     = 1000;
constexpr uint16_t PWM_NEUTRAL = 1500;
constexpr uint16_t PWM_MAX     = 2000;

constexpr uint32_t INIT_DELAY_MS = 2000; // ESC Başlatma Bekleme Süresi
}

// ------------------------------------------------------------------------
// 5. MOTOR / AXIS CONSTRAINTS
// ------------------------------------------------------------------------
namespace Motor {
constexpr int8_t PERCENT_MIN = -100;
constexpr int8_t PERCENT_MAX = 100;
constexpr int8_t DEADZONE    = 3;    // %5'in altındaki joystik kaymalarını yoksay
}

// ------------------------------------------------------------------------
// 6. DEBUG CONFIGURATION (Serial Monitor Ayarları)
// ------------------------------------------------------------------------
namespace Debug {
constexpr bool ENABLE_DEBUG       = true;
constexpr unsigned long BAUDRATE  = 115200;
constexpr bool PRINT_PACKETS      = true;
constexpr bool PRINT_PARSED       = true;
constexpr bool PRINT_PWM          = false;
}

} // namespace Config

// ============================================================================
// UTILITIES MODULE
// ============================================================================
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

  if (denominator == 0) {
    return Config::ESC::PWM_NEUTRAL;
  }

  long result = pwmMin + (numerator / denominator);
  return (uint16_t)clamp(result, (long)pwmMin, (long)pwmMax);
}
}

// ============================================================================
// DATA STRUCTURES
// ============================================================================
struct MotorOutputs {
  int8_t m1; // Arka Sol
  int8_t m2; // Arka Sağ
  int8_t m3; // Ön Sol
  int8_t m4; // Ön Sağ
  int8_t m5; // Sol Dikey
  int8_t m6; // Sağ Dikey
};

struct ControlCommands {
  int8_t forward;
  int8_t strafe;
  int8_t yaw;
  int8_t vertical;
  bool emergencyStop;
  bool isValid;
};

// ============================================================================
// ESC CONTROLLER CLASS
// ============================================================================
class ESCController {
  public:
    ESCController() {
      for (uint8_t i = 0; i < Config::Hardware::THRUSTER_COUNT; ++i) {
        m_currentPWM[i] = Config::ESC::PWM_NEUTRAL;
      }
    }

    void begin() {
      const uint8_t pins[Config::Hardware::THRUSTER_COUNT] = {
        Config::Hardware::PIN_ESC_M1,
        Config::Hardware::PIN_ESC_M2,
        Config::Hardware::PIN_ESC_M3,
        Config::Hardware::PIN_ESC_M4,
        Config::Hardware::PIN_ESC_M5,
        Config::Hardware::PIN_ESC_M6
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
                            Config::Motor::PERCENT_MIN,
                            Config::Motor::PERCENT_MAX,
                            Config::ESC::PWM_MIN,
                            Config::ESC::PWM_MAX
                          );

      m_currentPWM[motorIndex] = pwmValue;
      m_escs[motorIndex].writeMicroseconds(pwmValue);

      if (Config::Debug::ENABLE_DEBUG && Config::Debug::PRINT_PWM) {
        Serial.print(F("M"));
        Serial.print(motorIndex + 1);
        Serial.print(F(" PWM: "));
        Serial.println(pwmValue);
      }
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

// ============================================================================
// MOTION CONTROLLER CLASS
// ============================================================================
class MotionController {
  public:
    MotionController() {}

    MotorOutputs calculateOutputs(int8_t f, int8_t s, int8_t y, int8_t v) {
      int8_t forward = Utilities::applyDeadzone(f, Config::Motor::DEADZONE);
      int8_t strafe  = Utilities::applyDeadzone(s, Config::Motor::DEADZONE);
      int8_t yaw     = Utilities::applyDeadzone(y, Config::Motor::DEADZONE);
      int8_t vert    = Utilities::applyDeadzone(v, Config::Motor::DEADZONE);

      MotorOutputs outputs = {0, 0, 0, 0, 0, 0};

      // Dikey Eksen (M5 ve M6)
      outputs.m5 = vert;
      outputs.m6 = vert;

      // İleri/Geri Eksen (M1 ve M2)
      outputs.m1 = forward;
      outputs.m2 = forward;

      // Dönüş / Yaw Ekseni (M3 ve M4)
      if (yaw > 0) {
        outputs.m3 = yaw;
        outputs.m4 = 0;
      } else if (yaw < 0) {
        outputs.m3 = 0;
        outputs.m4 = -yaw;
      } else {
        outputs.m3 = 0;
        outputs.m4 = 0;
      }

      // Yanal Kayma / Strafe Mantığı (Sadece robot dururken)
      if (strafe != 0 && forward == 0 && yaw == 0) {
        outputs.m1 = strafe;
        outputs.m3 = strafe;
        outputs.m2 = -strafe;
        outputs.m4 = -strafe;
      }

      // Yazılımsal Invert (Yön Çevirme) Uygulaması
      outputs.m1 *= Config::MotorDirection::INVERT_M1;
      outputs.m2 *= Config::MotorDirection::INVERT_M2;
      outputs.m3 *= Config::MotorDirection::INVERT_M3;
      outputs.m4 *= Config::MotorDirection::INVERT_M4;
      outputs.m5 *= Config::MotorDirection::INVERT_M5;
      outputs.m6 *= Config::MotorDirection::INVERT_M6;

      // Sınırlandırma (-100 ile %100 arası)
      outputs.m1 = Utilities::clamp(outputs.m1, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m2 = Utilities::clamp(outputs.m2, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m3 = Utilities::clamp(outputs.m3, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m4 = Utilities::clamp(outputs.m4, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m5 = Utilities::clamp(outputs.m5, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);
      outputs.m6 = Utilities::clamp(outputs.m6, Config::Motor::PERCENT_MIN, Config::Motor::PERCENT_MAX);

      return outputs;
    }
};

// ============================================================================
// PACKET PARSER CLASS
// ============================================================================
class PacketParser {
  public:
    PacketParser() {}

    ControlCommands parsePacket(const char* buffer, uint16_t length) {
      ControlCommands cmds = {0, 0, 0, 0, false, false};

      if (buffer == nullptr || length == 0) return cmds;

      // Acil Durdurma kontrolü (Pakette "STOP" veya "EMERGENCY" geçerse)
      if (strstr(buffer, "STOP") != nullptr || strstr(buffer, "EMERGENCY") != nullptr) {
        cmds.emergencyStop = true;
        cmds.isValid = true;
        return cmds;
      }

      cmds.forward  = extractValue(buffer, 'F');
      cmds.strafe   = extractValue(buffer, 'S');
      cmds.vertical = extractValue(buffer, 'V');
      cmds.yaw      = extractValue(buffer, 'Y');
      cmds.isValid  = true;

      if (Config::Debug::ENABLE_DEBUG && Config::Debug::PRINT_PARSED) {
        Serial.print(F("Parsed -> F: "));
        Serial.print(cmds.forward);
        Serial.print(F(" | S: "));
        Serial.print(cmds.strafe);
        Serial.print(F(" | V: "));
        Serial.print(cmds.vertical);
        Serial.print(F(" | Y: "));
        Serial.println(cmds.yaw);
      }

      return cmds;
    }

  private:
    int8_t extractValue(const char* buffer, char key) {
      const char* ptr = strchr(buffer, key);
      if (ptr == nullptr) return 0;

      ptr++;
      while (*ptr == ':' || *ptr == ' ' || *ptr == '=') {
        ptr++;
      }

      int val = atoi(ptr);
      return (int8_t)Utilities::clamp(val, (int)Config::Motor::PERCENT_MIN, (int)Config::Motor::PERCENT_MAX);
    }
};

// ============================================================================
// ETHERNET RECEIVER CLASS
// ============================================================================
class EthernetReceiver {
  public:
    EthernetReceiver()
      : m_ip(Config::Network::IP_ADDRESS[0], Config::Network::IP_ADDRESS[1],
             Config::Network::IP_ADDRESS[2], Config::Network::IP_ADDRESS[3]) {
      for (uint8_t i = 0; i < 6; ++i) {
        m_mac[i] = Config::Network::MAC_ADDRESS[i];
      }
    }
    void begin() {
      // Wokwi'de Ethernet (W5500) CS pini genelde 10 numaralı pindir.
      Ethernet.init(10);

      // Statik IP yapılandırması: MAC, IP, DNS, Gateway, Subnet
      IPAddress gateway(Config::Network::GATEWAY[0], Config::Network::GATEWAY[1], Config::Network::GATEWAY[2], Config::Network::GATEWAY[3]);
      IPAddress subnet(Config::Network::SUBNET[0], Config::Network::SUBNET[1], Config::Network::SUBNET[2], Config::Network::SUBNET[3]);

      Ethernet.begin(m_mac, m_ip, gateway, gateway, subnet);
      m_udp.begin(Config::Network::LOCAL_PORT);

      if (Config::Debug::ENABLE_DEBUG) {
        Serial.print(F("Ethernet Ready. IP: "));
        Serial.println(Ethernet.localIP());
        Serial.print(F("UDP Listening on port: "));
        Serial.println(Config::Network::LOCAL_PORT);
      }
    }
    uint16_t readPacket(char* outputBuffer, uint16_t maxLen) {
      int packetSize = m_udp.parsePacket();
      if (packetSize <= 0) return 0;

      int len = m_udp.read(outputBuffer, maxLen - 1);
      if (len > 0) {
        outputBuffer[len] = '\0';
      }

      if (Config::Debug::ENABLE_DEBUG && Config::Debug::PRINT_PACKETS) {
        Serial.print(F("Rx Packet ["));
        Serial.print(len);
        Serial.print(F(" bytes]: "));
        Serial.println(outputBuffer);
      }

      return (uint16_t)len;
    }

  private:
    EthernetUDP m_udp;
    byte m_mac[6];
    IPAddress m_ip;
};

// ============================================================================
// GLOBAL INSTANCES & MAIN PROGRAM LOOP
// ============================================================================
ESCController      escController;
MotionController    motionController;
PacketParser        packetParser;
EthernetReceiver    ethernetReceiver;

char packetBuffer[Config::Network::BUFFER_SIZE];

unsigned long lastPacketTime = 0;
constexpr unsigned long WATCHDOG_TIMEOUT_MS = 1000; // 1 Saniye sinyal gelmezse motorları durdur

void setup() {
  if (Config::Debug::ENABLE_DEBUG) {
    Serial.begin(Config::Debug::BAUDRATE);
    while (!Serial && millis() < 3000);
    Serial.println(F("========================================"));
    Serial.println(F(" ROV Competition Firmware Initializing "));
    Serial.println(F("========================================"));
  }

  escController.begin();
  ethernetReceiver.begin();

  lastPacketTime = millis();

  if (Config::Debug::ENABLE_DEBUG) {
    Serial.println(F("ROV System Online and Ready. Waiting for commands..."));
  }
}

void loop() {
  uint16_t bytesRead = ethernetReceiver.readPacket(packetBuffer, Config::Network::BUFFER_SIZE);

  if (bytesRead > 0) {
    lastPacketTime = millis();

    ControlCommands cmds = packetParser.parsePacket(packetBuffer, bytesRead);

    if (cmds.isValid) {
      if (cmds.emergencyStop) {
        escController.stopAll();
        if (Config::Debug::ENABLE_DEBUG) {
          Serial.println(F("!!! EMERGENCY STOP TRIGGERED !!!"));
        }
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

  // Fail-Safe Watchdog (Bağlantı koparsa güvenli duruş)
  if (millis() - lastPacketTime > WATCHDOG_TIMEOUT_MS) {
    escController.stopAll();
  }
}
