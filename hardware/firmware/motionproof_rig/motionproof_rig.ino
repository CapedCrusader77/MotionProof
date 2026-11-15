// MotionProof test rig firmware (protocol version 1), ESP32 + step/dir driver + AS5600.
//
// NOT YET COMPILED OR RUN ON HARDWARE. Review every pin and constant against your build.
//
// Hardware assumed:
//   - ESP32 DevKit (any ESP32 with Arduino core 2.x or 3.x)
//   - Step/dir driver (A4988, DRV8825 or TMC2209 in step/dir mode) driving the NEMA 17
//   - AS5600 magnetic encoder on the gearbox OUTPUT shaft, I2C (12 bit, 4096 counts/rev)
//   - Emergency stop: a normally closed switch that ALSO cuts motor power in hardware.
//     Its auxiliary contact goes to PIN_ESTOP (closed = GND = OK, open = stop).
//   - Optional limit switches on PIN_LIMIT (closed = GND = OK).
// Motor angle is taken from the commanded step count (open loop). A missed step is therefore
// not seen on the input channel; compare input and output motion to detect it.
//
// Library: ArduinoJson 7 (Library Manager).
//
// Protocol: newline-delimited JSON at 115200 baud, see docs/device-protocol.md.

#include <Arduino.h>
#include <ArduinoJson.h>
#include <Wire.h>

// ---------------------------------------------------------------- configuration
static const int PIN_STEP = 25;
static const int PIN_DIR = 26;
static const int PIN_EN = 27;      // driver enable, active LOW
static const int PIN_ESTOP = 32;   // NC e-stop auxiliary contact to GND, INPUT_PULLUP
static const int PIN_LIMIT = 33;   // NC limit switches in series to GND, INPUT_PULLUP

static const float MOTOR_STEPS_PER_REV = 200.0f;
static const float MICROSTEPS = 16.0f;
static const float NOMINAL_RATIO = 33.0f;          // design target; the rig measures the real one
static const float ENCODER_COUNTS = 4096.0f;       // AS5600
static const int OUTPUT_SIGN = 1;                  // +1 or -1 so that output follows command
static const uint32_t TELEMETRY_PERIOD_US = 5000;  // 200 Hz
static const uint32_t HOST_TIMEOUT_MS = 500;       // stop if no command for this long
static const float MAX_STEP_RATE = 20000.0f;       // steps/s hard cap

static const uint8_t AS5600_ADDR = 0x36;
static const uint8_t AS5600_RAW_ANGLE = 0x0C;
static const char *DEVICE_ID = "RIG-01";
static const char *FIRMWARE = "motionproof-rig 0.1.0";

// ---------------------------------------------------------------- state
static const float COUNTS_PER_MOTOR_REV = MOTOR_STEPS_PER_REV * MICROSTEPS;
volatile long stepPosition = 0;   // microsteps, motor side
volatile long stepTarget = 0;
hw_timer_t *stepTimer = nullptr;

bool armed = false;
bool moving = false;
uint32_t lastHostMs = 0;
uint32_t seq = 0;
uint64_t moveStartUs = 0;
uint64_t lastTelemetryUs = 0;
long outputTurns = 0;
int lastRaw = -1;
float armOutput = 0.0f;   // absolute encoder angle at arm time, rad
float planStart = 0.0f;   // first commanded angle of the test, rad

struct Test {
  bool reversal = true;
  float centre = 0, excursion = 0, moveTime = 1, settle = 0.4, preSettle = 0.25;
  int cycles = 1;
} test;

// knots of the rest-to-rest quintic plan (same sequence as motionproof.simulation.tasks)
static const int MAX_KNOTS = 256;
float knotT[MAX_KNOTS];
float knotQ[MAX_KNOTS];
int knots = 0;

// ---------------------------------------------------------------- helpers
void IRAM_ATTR onStepTimer() {
  long diff = stepTarget - stepPosition;
  if (diff == 0) return;
  bool fwd = diff > 0;
  digitalWrite(PIN_DIR, fwd ? HIGH : LOW);
  digitalWrite(PIN_STEP, HIGH);
  delayMicroseconds(2);
  digitalWrite(PIN_STEP, LOW);
  stepPosition += fwd ? 1 : -1;
}

int readRawAngle() {
  Wire.beginTransmission(AS5600_ADDR);
  Wire.write(AS5600_RAW_ANGLE);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom((int)AS5600_ADDR, 2) != 2) return -1;
  int hi = Wire.read(), lo = Wire.read();
  return ((hi & 0x0F) << 8) | lo;
}

// Multi-turn output angle in rad; returns NAN on a sensor fault.
float outputAngle(long *countsOut) {
  int raw = readRawAngle();
  if (raw < 0) return NAN;
  if (lastRaw >= 0) {
    int d = raw - lastRaw;
    if (d > 2048) outputTurns--;
    if (d < -2048) outputTurns++;
  }
  lastRaw = raw;
  long counts = outputTurns * (long)ENCODER_COUNTS + raw;
  *countsOut = counts;
  return OUTPUT_SIGN * counts * TWO_PI / ENCODER_COUNTS;
}

// The rig is placed at the test's first commanded angle before arming; both channels are
// reported in that frame: plan start + motion since arming.
float motorAngleOutputReferred() {
  return planStart + stepPosition * TWO_PI / (COUNTS_PER_MOTOR_REV * NOMINAL_RATIO);
}

void stopMotion(const char *state, const char *reason) {
  stepTarget = stepPosition;
  digitalWrite(PIN_EN, HIGH);
  bool wasMoving = moving;
  moving = false;
  armed = false;
  if (wasMoving || strcmp(state, "done") != 0) {
    JsonDocument doc;
    doc["type"] = "status";
    doc["state"] = state;
    if (reason) doc["reason"] = reason;
    serializeJson(doc, Serial);
    Serial.println();
  }
}

void addKnot(float dt, float q) {
  if (knots >= MAX_KNOTS) return;
  knotT[knots] = knots ? knotT[knots - 1] + dt : 0.0f;
  knotQ[knots] = q;
  knots++;
}

void buildPlan() {
  knots = 0;
  float c = test.centre, e = test.excursion;
  if (test.reversal) {
    addKnot(0, c - e);
    addKnot(test.preSettle, c - e);
    addKnot(test.moveTime, c);
    addKnot(test.settle, c);
    addKnot(test.moveTime, c + e);
    addKnot(test.settle, c + e);
    addKnot(test.moveTime, c);
    addKnot(test.settle, c);
  } else {
    addKnot(0, c);
    addKnot(test.preSettle, c);
    for (int i = 0; i < test.cycles; i++) {
      addKnot(test.moveTime, c + e);
      addKnot(test.settle, c + e);
      addKnot(test.moveTime, c);
      addKnot(test.settle, c);
    }
  }
}

float commandAt(float t) {
  if (knots == 0) return 0;
  if (t <= knotT[0]) return knotQ[0];
  if (t >= knotT[knots - 1]) return knotQ[knots - 1];
  int i = 0;
  while (i < knots - 2 && t >= knotT[i + 1]) i++;
  float s = (t - knotT[i]) / (knotT[i + 1] - knotT[i]);
  float blend = s * s * s * (10 - 15 * s + 6 * s * s);
  return knotQ[i] + (knotQ[i + 1] - knotQ[i]) * blend;
}

long stepsForOutput(float qOut) {
  return lroundf((qOut - planStart) * COUNTS_PER_MOTOR_REV * NOMINAL_RATIO / TWO_PI);
}

void sendHello() {
  JsonDocument doc;
  doc["type"] = "hello";
  doc["device"] = DEVICE_ID;
  doc["firmware"] = FIRMWARE;
  doc["nominal_ratio"] = NOMINAL_RATIO;
  JsonObject sensors = doc["sensors"].to<JsonObject>();
  sensors["input_encoder_counts"] = COUNTS_PER_MOTOR_REV;  // microsteps per motor rev
  sensors["input_is_open_loop"] = true;
  sensors["output_encoder_counts"] = ENCODER_COUNTS;
  sensors["torque"] = false;
  sensors["current"] = false;
  sensors["temperature"] = false;
  serializeJson(doc, Serial);
  Serial.println();
}

void handleCommand(const char *line) {
  JsonDocument doc;
  if (deserializeJson(doc, line)) return;  // ignore malformed host lines
  lastHostMs = millis();
  const char *cmd = doc["cmd"] | "";
  if (!strcmp(cmd, "ping")) {
    if (!moving) sendHello();
  } else if (!strcmp(cmd, "arm")) {
    if (digitalRead(PIN_ESTOP) == HIGH) { stopMotion("stopped", "emergency stop open"); return; }
    long c;
    float o = outputAngle(&c);
    if (isnan(o)) { stopMotion("fault", "output encoder not readable"); return; }
    armOutput = o;
    stepPosition = stepTarget = 0;
    digitalWrite(PIN_EN, LOW);
    armed = true;
  } else if (!strcmp(cmd, "move")) {
    if (!armed) { stopMotion("stopped", "move refused: not armed"); return; }
    JsonObject t = doc["test"];
    test.reversal = strcmp(t["kind"] | "reversal", "cycles") != 0;
    test.centre = t["centre"] | 0.0f;
    test.excursion = t["excursion"] | 0.0f;
    test.moveTime = t["move_time"] | 1.0f;
    test.settle = t["settle"] | 0.4f;
    test.cycles = t["cycles"] | 1;
    buildPlan();
    planStart = knotQ[0];  // the output was placed at the plan's first point before arming
    seq = 0;
    moveStartUs = esp_timer_get_time();
    lastTelemetryUs = 0;
    moving = true;
  } else if (!strcmp(cmd, "stop")) {
    stopMotion("stopped", "host stop");
  }
}

// ---------------------------------------------------------------- Arduino
void setup() {
  pinMode(PIN_STEP, OUTPUT);
  pinMode(PIN_DIR, OUTPUT);
  pinMode(PIN_EN, OUTPUT);
  digitalWrite(PIN_EN, HIGH);  // driver disabled until armed
  pinMode(PIN_ESTOP, INPUT_PULLUP);
  pinMode(PIN_LIMIT, INPUT_PULLUP);
  Serial.begin(115200);
  Wire.begin();
  Wire.setClock(400000);
  // 1 MHz timer, interrupt at the hard step-rate cap
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  stepTimer = timerBegin(1000000);
  timerAttachInterrupt(stepTimer, &onStepTimer);
  timerAlarm(stepTimer, (uint64_t)(1e6f / MAX_STEP_RATE), true, 0);
#else
  stepTimer = timerBegin(0, 80, true);
  timerAttachInterrupt(stepTimer, &onStepTimer, true);
  timerAlarmWrite(stepTimer, (uint64_t)(1e6f / MAX_STEP_RATE), true);
  timerAlarmEnable(stepTimer);
#endif
  lastHostMs = millis();
}

void loop() {
  static char buf[512];
  static size_t len = 0;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\n') {
      buf[len] = 0;
      handleCommand(buf);
      len = 0;
    } else if (len < sizeof(buf) - 1) {
      buf[len++] = ch;
    }
  }
  if (!moving) return;

  if (millis() - lastHostMs > HOST_TIMEOUT_MS) { stopMotion("stopped", "host timeout"); return; }
  uint8_t flags = 0;
  if (digitalRead(PIN_ESTOP) == HIGH) flags |= 1;
  if (digitalRead(PIN_LIMIT) == HIGH) flags |= 2;

  uint64_t nowUs = esp_timer_get_time() - moveStartUs;
  float t = nowUs * 1e-6f;
  float q = commandAt(t);
  stepTarget = stepsForOutput(q);

  if (nowUs - lastTelemetryUs >= TELEMETRY_PERIOD_US || lastTelemetryUs == 0) {
    lastTelemetryUs = nowUs;
    long outCounts = 0;
    float out = outputAngle(&outCounts);
    if (isnan(out)) flags |= 8;
    JsonDocument doc;
    doc["type"] = "telemetry";
    doc["seq"] = seq++;
    doc["t_us"] = (uint32_t)nowUs;
    doc["command_rad"] = q;
    doc["input_angle_rad"] = motorAngleOutputReferred();
    if (isnan(out)) doc["output_angle_rad"] = nullptr;
    else doc["output_angle_rad"] = planStart + (out - armOutput);
    doc["input_counts"] = (int32_t)stepPosition;
    doc["output_counts"] = (int32_t)outCounts;
    doc["torque_nm"] = nullptr;
    doc["current_a"] = nullptr;
    doc["temp_c"] = nullptr;
    doc["flags"] = flags;
    serializeJson(doc, Serial);
    Serial.println();
  }
  if (flags & 1) { stopMotion("stopped", "emergency stop"); return; }
  if (flags & 2) { stopMotion("stopped", "limit switch"); return; }
  if (t >= knotT[knots - 1] + 0.05f) stopMotion("done", nullptr);
}
