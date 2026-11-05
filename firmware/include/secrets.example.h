#pragma once
// Copy to secrets.h (ignored by Git). Never commit credentials.
#define WIFI_SSID "REPLACE_ME"
#define WIFI_PASSWORD "REPLACE_ME"
#define API_BASE "https://YOUR_SERVER"
#define DEVICE_ID "atom-entrance-a"
#define DEVICE_TOKEN "REPLACE_WITH_ISSUED_DEVICE_TOKEN"
// Root CA PEM matching your server's certificate chain. Never use setInsecure().
#define ROOT_CA "-----BEGIN CERTIFICATE-----\nREPLACE_ME\n-----END CERTIFICATE-----\n"
// ATOM Lite Grove I2C: SDA G26 / SCL G32. Verify cable pin labels before wiring.
#define SDA_PIN 26
#define SCL_PIN 32
// Starting calibration values ONLY. Measure the actual floor/head distances.
#define DETECT_MM 1500
#define RELEASE_MM 1650
#define ROI_A_CENTER 167
#define ROI_B_CENTER 231
#define ROI_WIDTH 4
#define ROI_HEIGHT 8
