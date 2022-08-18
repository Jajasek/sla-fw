# Tilt/Tower moving profiles

- set of all tilt/tower profiles
- values are copied to MC
- see `slafw/hardware/sl1/tilt_profiles.py:MovingProfilesTiltSL1` to get the names of Tilt profiles
- see `slafw/hardware/sl1/tower_profiles.py:MovingProfilesTowerSL1` to get the names of Tower profiles


# Layer and exposure profiles

- set of values for exposure management
- values are stored in A64
- tilt move procedure:
    1. set `initial_profile` (see Tilt moving Profiles)
    2. go number of `offset_steps`
    3. wait `offset_delay_ms`
    4. set `finish_profile`
    5. split rest of the distence to X `cycles`
    6. wait `delay_ms` between `cycles`
    7. home when moving down
- see `slafw/exposure/profiles.py:LayerProfilesSL1` to get the names of the profiles
- see `slafw/exposure/profiles.py:SingleLayerProfileSL1` to get profile items description
