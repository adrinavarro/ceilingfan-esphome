# One RF bridge hosts many device profiles

`ceilingfan-esphome` will model every physical fan installation as a separate device
profile while allowing one ESP32 and CC1101 RF bridge to host many profiles. Profiles
may share a protocol adapter but never a remote identity; transmissions are serialized
through the shared radio. Static raw waveforms remain the compatibility fallback,
while dynamic protocols are not advertised as supported until their changing fields
can be generated and physically validated. This boundary prevents identical fans in
different rooms from becoming one ambiguous device and lets new RF formats be added
without duplicating the installed control bridge.
