# Hardware

## Shopping list for normal use

| Quantity | Item | Notes |
|---:|---|---|
| 1 | ESP32 DevKitC-compatible development board | Must be compatible with ESPHome's `esp32dev` definition and expose 3.3 V, GPIO14, GPIO18, GPIO19, GPIO23, GPIO26, and GPIO27. |
| 1 | CC1101 transceiver module with matching antenna | For the currently supported catalog, use a 433 MHz module and antenna. Other remotes may use 315, 868, or 915 MHz. |
| 1 | Female-to-female Dupont jumper set | Both common boards normally have male headers. Eight conductors are used. A 40-wire, 20 cm ribbon can be separated as required. |
| 1 | Data-capable USB cable | Required for the initial ESP32 flash. Charge-only cables do not work. |
| 1 | 5 V USB power supply | Powers the installed bridge. The CC1101 itself uses the ESP32's 3.3 V pin. |
| 1 | Original ceiling fan remote | Used for bridge-based learning and physical validation. |

**No RTL-SDR is required for normal setup, bridge-based learning, deployment, or
operation.** The CC1101 is a transceiver: the learning firmware configures its GDO2 pin as a
receiver, while final firmware uses GDO0 to transmit learned commands.

### Reference purchase

The first working bridge used these products from Tiendatec.es:

| Quantity | Purchased item |
|---:|---|
| 1 | 40-wire, 20 cm female-to-female Dupont cable ribbon |
| 1 | 433 MHz CC1101 RF transceiver with antenna |
| 1 | ESP32 DevKitC V4 Wi-Fi + Bluetooth 4 MB IoT board |

Those three items cost **EUR 17.90 plus shipping** at the time of purchase. The price
does not include a USB data cable or final USB supply and may change. A local supplier
can be competitive for a small order once shipping, import duties, and per-item
marketplace fees are included.

## Optional equipment for advanced research

| Quantity | Item | When it helps |
|---:|---|---|
| 1 | Basic RTL2832U RTL-SDR receiver | Wide spectrum discovery and raw I/Q capture for an unsupported or poorly understood remote. Entry-level units have been found for about EUR 18 plus shipping. |
| 1 | RTL-SDR antenna covering the candidate band | Used only with the optional receiver. A basic telescopic antenna is adequate at short range. |

This research equipment is a nice-to-have for protocol contributors, not a purchase
prerequisite for users of a supported family. Use it when the frequency or modulation
is unknown, when the narrow-band CC1101 settings cannot yet be chosen, or when raw
I/Q data is necessary to investigate framing, FSK, or changing fields. See
[Advanced RTL-SDR research](advanced-rtl-research.md).

## Reference assembly

| CC1101 | ESP32 | Purpose |
|---|---|---|
| VCC | 3V3 | Power |
| GND | GND | Ground |
| SCK | GPIO18 | SPI clock |
| MOSI / SI | GPIO23 | SPI controller output |
| MISO / SO | GPIO19 | SPI controller input |
| CSN / SS | GPIO14 | SPI chip select |
| GDO0 | GPIO26 | RF transmission |
| GDO2 | GPIO27 | RF reception and learning |

Separate receive and transmit data pins let the CC1101 change radio modes without
reassigning a GPIO at runtime. GDO0 must not be declared as a second conflicting
GPIO owner.

## Selecting a radio band

All protocol families presently in the catalog were captured at 433.92 MHz ASK/OOK,
so a correctly matched 433 MHz CC1101 module and antenna cover those known devices.
This is not a universal ceiling-fan standard.

For a supported model, follow its catalog entry. For an unsupported remote, first
check its case, battery compartment, manual, regulatory identifiers, and product
documentation. Only if the band remains uncertain is an optional RTL-SDR spectrum
scan useful before buying a band-specific CC1101 module.

The CC1101 chip can tune across multiple sub-GHz bands, but modules are sold with
matching networks optimized for particular bands. A 433 MHz module may perform
poorly at 868/915 MHz even when the chip accepts that frequency.

## Electrical and radio safety

- Power the CC1101 from 3.3 V only.
- Disconnect power before changing wiring.
- Fit an antenna designed for the selected band before transmitting.
- Start at 0 dBm and increase power only when installed range requires it.
- Follow local spectrum, duty-cycle, and output-power regulations.
