// Valve control with a CONTINUOUS-ROTATION servo (MG996R on GPIO13), by timing.
// On this kind of servo the number you send is a speed and direction, not an angle:
// 90 = stop, above 90 = spin one way, below 90 = spin the other way.
//
// Library (Library Manager): "ESP32Servo" by Kevin Harrington.
// Serial Monitor: 115200 baud, line ending "Newline".
//
// Teach it once (saved in flash, survives power-off):
//   f<ms>     spin FORWARD (above 90) for that many ms, then stop    e.g.  f300
//   b<ms>     spin BACKWARD (below 90) for that many ms, then stop   e.g.  b300
//   open f    forward is the OPEN direction   (or: open b)
//   to<ms>    time the servo spins to OPEN the valve                 e.g.  to800
//   tc<ms>    time the servo spins to CLOSE the valve                e.g.  tc600
//   sp<n>     speed: how far from 90 to spin (default 10, range 4..40)
//   o / c     open / close the valve (spin the saved time, then stop)
//   x         stop at once (servo limp)
//   p         print saved settings
//
// The servo is only powered while it moves; between moves it is limp. A big run time against
// the valve's end stop makes the servo strain, so tune t a little SHORT of a full turn.

#include <ESP32Servo.h>
#include <Preferences.h>

const int PIN_SERVO = 13;
const int STOP_US_ANGLE = 90;
const int MAX_RUN_MS = 3000;

Servo servo;
Preferences prefs;
int speedOffset = 10;
int openDir = 0;        // +1: forward opens, -1: backward opens, 0: not set
int openMs = 0;         // time to open, 0: not set
int closeMs = 0;        // time to close, 0: not set

void run(int dir, int ms) {   // dir +1 forward, -1 backward
  if (ms <= 0) return;
  if (ms > MAX_RUN_MS) ms = MAX_RUN_MS;
  servo.setPeriodHertz(50);
  servo.attach(PIN_SERVO, 500, 2400);
  servo.write(STOP_US_ANGLE + dir * speedOffset);
  delay(ms);
  servo.write(STOP_US_ANGLE);
  delay(100);
  servo.detach();
  Serial.print(dir > 0 ? "forward " : "backward ");
  Serial.print(ms);
  Serial.println(" ms done");
}

void printSettings() {
  Serial.print("speed=");
  Serial.print(speedOffset);
  Serial.print("  open direction=");
  Serial.print(openDir > 0 ? "forward" : (openDir < 0 ? "backward" : "not set"));
  Serial.print("  open time=");
  if (openMs > 0) { Serial.print(openMs); Serial.print(" ms"); } else Serial.print("not set");
  Serial.print("  close time=");
  if (closeMs > 0) { Serial.print(closeMs); Serial.println(" ms"); } else Serial.println("not set");
}

void setup() {
  Serial.begin(115200);
  delay(500);
  prefs.begin("valve", false);
  speedOffset = prefs.getInt("speed", 10);
  openDir = prefs.getInt("dir", 0);
  openMs = prefs.getInt("to", prefs.getInt("t", 0));
  closeMs = prefs.getInt("tc", prefs.getInt("t", 0));
  Serial.println("Valve servo ready (timed). Commands: f<ms> b<ms> open f|b t<ms> sp<n> o c x p");
  printSettings();
}

void loop() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd == "o" || cmd == "c") {
    int ms = (cmd == "o") ? openMs : closeMs;
    if (openDir == 0 || ms <= 0) {
      Serial.println("not set up yet: use  open f|b  then  to<ms>  and  tc<ms>");
      return;
    }
    run(cmd == "o" ? openDir : -openDir, ms);
  } else if (cmd == "x") {
    servo.detach();
    Serial.println("stopped (limp)");
  } else if (cmd == "p") {
    printSettings();
  } else if (cmd == "open f" || cmd == "open b") {
    openDir = (cmd == "open f") ? 1 : -1;
    prefs.putInt("dir", openDir);
    Serial.println(openDir > 0 ? "OPEN = forward" : "OPEN = backward");
  } else if (cmd.startsWith("sp")) {
    int n = cmd.substring(2).toInt();
    if (n < 4 || n > 40) { Serial.println("speed must be 4..40"); return; }
    speedOffset = n;
    prefs.putInt("speed", speedOffset);
    Serial.print("speed = ");
    Serial.println(speedOffset);
  } else if (cmd.startsWith("to") || cmd.startsWith("tc")) {
    int n = cmd.substring(2).toInt();
    if (n < 50 || n > MAX_RUN_MS) { Serial.println("time must be 50..3000 ms"); return; }
    if (cmd.charAt(1) == 'o') { openMs = n; prefs.putInt("to", n); Serial.print("open time = "); }
    else { closeMs = n; prefs.putInt("tc", n); Serial.print("close time = "); }
    Serial.print(n);
    Serial.println(" ms");
  } else if (cmd.charAt(0) == 'f') {
    run(+1, cmd.substring(1).toInt());
  } else if (cmd.charAt(0) == 'b') {
    run(-1, cmd.substring(1).toInt());
  } else {
    Serial.println("unknown command");
  }
}
