// Prints real sensor readings as one JSON line every 500 ms over USB serial.
// tools/serial_bridge.py forwards each line to the gateway dashboard.
//
// Libraries (Library Manager): Adafruit INA219, OneWire, DallasTemperature,
// "HX711 Arduino Library" by Bogdan Necula.
//
// Pins: INA219 SDA=21 SCL=22, DS18B20 DATA=4 (4.7k pull-up to 3V3), HX711 DT=25 SCK=26.
// A sensor that fails to read is left out of the line. Values are never invented.

#include <Wire.h>
#include <Adafruit_INA219.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include "HX711.h"

const int PIN_SDA = 21, PIN_SCL = 22;
const int PIN_DS18B20 = 4;
const int PIN_HX_DT = 25, PIN_HX_SCK = 26;

// 0 = load cell not calibrated yet: only raw counts are sent.
// After calibration set this to (raw counts per gram) and HX_OFFSET to the tare raw value.
const float HX_COUNTS_PER_GRAM = 0.0;
const long HX_OFFSET = 0;

Adafruit_INA219 ina;
OneWire oneWire(PIN_DS18B20);
DallasTemperature ds18b20(&oneWire);
HX711 scale;
bool inaOk = false;

void setup() {
  Serial.begin(115200);
  Wire.begin(PIN_SDA, PIN_SCL);
  inaOk = ina.begin();
  ds18b20.begin();
  ds18b20.setWaitForConversion(false);
  ds18b20.requestTemperatures();
  scale.begin(PIN_HX_DT, PIN_HX_SCK);
}

void loop() {
  String line = "{";
  bool first = true;

  if (inaOk) {
    float volts = ina.getBusVoltage_V();
    float amps = ina.getCurrent_mA() / 1000.0;
    if (isfinite(volts) && isfinite(amps)) {
      line += "\"ina219\":{\"volts\":" + String(volts, 3) + ",\"amps\":" + String(amps, 4) + "}";
      first = false;
    }
  }

  float tempC = ds18b20.getTempCByIndex(0);
  ds18b20.requestTemperatures();
  if (tempC != DEVICE_DISCONNECTED_C && tempC > -55.0 && tempC < 125.0) {
    line += String(first ? "" : ",") + "\"ds18b20\":{\"temp_c\":" + String(tempC, 2) + "}";
    first = false;
  }

  if (scale.is_ready()) {
    long raw = scale.read();
    line += String(first ? "" : ",") + "\"hx711\":{\"raw\":" + String(raw);
    if (HX_COUNTS_PER_GRAM != 0.0) {
      line += ",\"mass_g\":" + String((raw - HX_OFFSET) / HX_COUNTS_PER_GRAM, 1);
    }
    line += "}";
    first = false;
  }

  line += "}";
  if (!first) Serial.println(line);
  delay(500);
}
