# Hardware

## Shopping list

### Required bridge components

| Quantity | Item | Notes |
|---:|---|---|
| 1 | ESP32 DevKitC-compatible development board | Must be compatible with ESPHome's `esp32dev` board definition and expose 3.3 V, GPIO14, GPIO18, GPIO19, GPIO23, GPIO26, and GPIO27. |
| 1 | CC1101 transceiver module with a matching antenna | Buy the module and antenna variant designed for the remote's frequency band, commonly 315, 433, 868, or 915 MHz. |
| 1 | Female-to-female Dupont jumper set | Both the ESP32 DevKitC and common CC1101 modules normally have male header pins. The bridge uses eight conductors for power, SPI, GDO0, and GDO2. A 40-wire, 20 cm female-to-female ribbon can be separated into the required individual wires. |
| 1 | Data-capable USB cable for the ESP32 | The connector depends on the development board. Charge-only cables cannot perform the initial flash. |
| 1 | 5 V USB power supply | Powers the completed bridge after onboarding. The CC1101 itself is powered from the ESP32's 3.3 V pin. |

### Required learning equipment

| Quantity | Item | Notes |
|---:|---|---|
| 1 | Basic RTL2832U-based RTL-SDR receiver | Required for the supported learning workflow. Entry-level units can be found for approximately EUR 18 plus shipping. It is used only for spectrum discovery and remote capture and is not part of the installed bridge. |
| 1 | RTL-SDR antenna covering the expected band | A basic telescopic antenna is sufficient when the remote is close to the receiver. |
| 1 | Original ceiling fan remote | Keep a working battery installed and have the fan available for controlled captures and validation. |

The CC1101 can receive and decode a clean ASK/OOK signal after its frequency,
modulation, symbol rate, and receiver settings are known. It is therefore useful for
later state synchronization or for capturing an already understood protocol. It is
not a practical substitute for an RTL-SDR during general discovery: it observes a
narrow configured channel and requires several of the unknown radio parameters to
be selected before a useful capture can be made. The RTL-SDR provides the spectrum
visibility and raw I/Q recordings needed by the learning phase.

### Reference purchase

The first working bridge used these three products from Tiendatec.es:

| Quantity | Purchased item |
|---:|---|
| 1 | 40-wire, 20 cm female-to-female Dupont cable ribbon |
| 1 | 433 MHz CC1101 RF transceiver with antenna |
| 1 | ESP32 DevKitC V4 Wi-Fi + Bluetooth 4 MB IoT board |

The three items cost **EUR 17.90 plus shipping** at the time of purchase. This price
does not include the RTL-SDR, USB data cable, or final USB power supply, and may
change. A local or regional supplier can be competitive for a small order once
shipping, import charges, and per-item marketplace fees are considered.

Do not buy the CC1101 or final antenna solely from the chip's advertised wide
frequency range. The module's matching network and antenna must suit the frequency
found during the learning phase. If the remote label does not state its frequency,
perform the RTL-SDR spectrum scan before ordering those two parts.

## Reference assembly

The reference design uses separate CC1101 data pins for transmission and reception:

- GDO0 to ESP32 GPIO26 for transmission.
- GDO2 to ESP32 GPIO27 for reception.
- SPI clock/data on GPIO18, GPIO23, and GPIO19.
- Chip select on GPIO14.

This dual-pin arrangement avoids changing the transmitter pin direction while the
CC1101 switches modes. GDO0 must not be declared as a second conflicting GPIO owner.

## Electrical safety

- Power the CC1101 from 3.3 V only.
- Disconnect power before changing wiring.
- Fit an antenna designed for the selected band before transmitting.
- Start at 0 dBm and increase power only when the installed range requires it.
- Follow local spectrum, duty-cycle, and output-power regulations.

## Radio compatibility

CC1101 modules are sold with matching networks optimized for different bands. A
module intended for 433 MHz may perform poorly at 868/915 MHz even if the chip can
be configured for that frequency.

The RTL-SDR is receive-only in this workflow. It discovers and records the original
remote; the CC1101 performs the final transmission.
