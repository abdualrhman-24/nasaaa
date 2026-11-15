# LUNA NAV AI accuracy report (NASA PDS LDEM_75S_240M, ldem_75s_240m.img)

| Check | Result | Measured | Reference | Tolerance |
|---|---|---|---|---|
| Shackleton depth (rim crest mean minus floor), NASA LOLA 240 m | PASS | 4.10 km | 4.1 km [R1] | ±0.4 km (240 m pixels smooth the rim) |
| Shackleton rim diameter, NASA LOLA 240 m | PASS | 20.6 km | 21 km [R1] | ±2.5 km |
| Our DEM-derived slope vs NASA official slope map (90 S to 87.5 S) | PASS | correlation 0.94, mean difference -0.7°, mean |difference| 1.0°, same 15° pass/block decision on 96.8% of cells | NASA LDSM_75S_240M [R5] | correlation ≥ 0.7 |
| Person 1 elevation (LDEM_75S_240M) minus LOLA 240 m, 6 sites | PASS | mean |diff| 0 m, max 0 m | same instrument, different gridding | mean ≤ 300 m |
| Person 1 slope minus LOLA 240 m slope | INFO | mean +0.0°, mean |diff| 0.0° | n/a |  |
| Person 1 candidate sites inside NASA Artemis III candidate regions | PASS | 1 of 6 within 7.5 km of a region centre; (-88.458,-67.8) 27.3 km from Connecting Ridge Extension; (-89.445,-137.3) 12.0 km from Connecting Ridge; (-88.807,123.6) 0.4 km from Peak Near Shackleton; (-89.311,-114.1) 10.9 km from Connecting Ridge Extension; (-88.666,-68.2) 22.4 km from Connecting Ridge Extension; (-89.779,-155.7) 22.6 km from Connecting Ridge | NASA Artemis III regions [R4] | ≥1 site inside a region |
| Shackleton floor sunlit fraction, 2020 (Person 2: Horizons + LOLA horizon) | PASS | 0.0% (REAL, 373 s) | 0% (permanent shadow) [R2] | ≤ 1% |
| Sunlit fraction at published peaks A-D | SKIP | skipped with --quick (each needs a full lunar year from Horizons) | 81-86% [R3] |  |
| End-to-end plan uses no MOCK values | PASS | statuses ['UNVERIFIED']; 6 candidates in 102 s | no MOCK |  |
| Visibility hours stay within the stay length | PASS | all ≤ 48 h | ≤ 48 h |  |
| Recommendation | INFO | site_d09ba45a8ac5 sunlight 48.0 h, Earth 26.3 h |  |  |

R1: Zuber et al., Nature 2012 (MIT News). R2: NASA SVS 4716. R3: Gläser et al. 2018 as tabulated on Wikipedia 'Peak of eternal light'. R4: NASA Artemis III candidate regions (2022), centres from Remote Sensing 17(9):1579. R5: NASA LOLA LDSM_75S_240M official slope map.