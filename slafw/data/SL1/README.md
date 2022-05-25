# Tilt/Tower moving profiles

- set of all tilt/tower profiles
- values are copied to MC
- see `slafw/hardware/sl1/tilt.py:MovingProfilesTiltSL1` to get the names of Tilt profiles
- see `slafw/hardware/sl1/tower.py:MovingProfilesTowerSL1` to get the names of Tower profiles


# Tune tilt profiles

- set of values for tilt movement while printing
```
[
    [tilt_down_large_fill],
    [tilt_down_small_fill],
    [tilt_up_large_fill],
    [tilt_up_small_fill],
]
```
- the movement is split on slow and fast by `limit for fast tilt` parameter
- values are stored in A64
-  tilt down procedure:
    1. set `initial profile` (the number of profile coresponds to TiltProfile(Enum))
    2. go number of `offset steps` [usteps]
    3. wait `offset delay` [ms]
    4. set `finish profile`
    5. split rest of the distence to X `tilt cycles`
    6. wait `tilt delay` between `tilt cycles`
    7. home (`homing cycles` defines number of retries)

## Structure of the file

```
[
    [initial profile, offset steps, offset delay, finish profile, tilt cycles, tilt delay, homing tolerance, homing cycles], # tilt down large fill (area > limit for fast tilt)
    [...], # tilt down small fill (area < limit for fast tilt)
    [...], # tilt up large fill (area > limit for fast tilt)
    [...]  # tilt up small fill (area < limit for fast tilt)
]
```
