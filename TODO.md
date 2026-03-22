## Shelly script management
- [ ] Build automation for uploading scripts to Shelly devices (PutCode + restart)
- [ ] Track which script version is deployed vs committed (hash comparison)
- [ ] Support multiple devices with per-device config (INPUT_ID, schedule, etc.)

## Local Tuya sensor polling (bypass cloud)
- [ ] Add tinytuya local polling for CO2 sensors (port 6668, AES-encrypted)
- [ ] Replace Homebridge CO2 path with direct local poll → actual 30s fresh readings
- [ ] Eliminates cloud dependency for CO2 (humidity already local via Shelly webhooks)

## Tighten nighttime CO2 thresholds
- [ ] Lower CO2 targets for sleeping hours (22-07): OFF→LOW at 700, LOW→HIGH at 900
- Studies show sleeping above 1000-1200 ppm measurably degrades sleep quality
- Could replace the fixed nighttime schedule with demand-controlled ventilation
  using these lower thresholds (smarter than dumb timer + smart sensor fighting)

## Consider lowering daytime HIGH threshold
- [ ] Current LOW→HIGH at 1200 ppm is conservative
- Consider 1000 ppm for HIGH, especially in bedrooms

## Rate-of-change trigger
- [ ] If CO2 rises >150 ppm between readings, kick fan to LOW immediately
- Anticipates threshold crossing (e.g. guests arrive, party)
- Caveat: with Tuya cloud's coarse reporting interval the derivative is noisy;
  becomes much more viable once local Tuya polling is in place

## Minimum LOW floor for occupied bedrooms at night
- [ ] Instead of cycling ON/OFF near the 800 ppm boundary all night,
  maintain minimum LOW speed during sleeping hours
- EC motors are near-silent at LOW — negligible acoustic penalty
- Steady low-flow beats intermittent bursts for comfort and energy
