# Tilt/Tower moving profiles

- set of all tilt/tower profiles
- values are copied to MC
- see `slafw/hardware/sl1/tilt_profiles.py:MovingProfilesTiltSL1` to get the
names of Tilt profiles
- see `slafw/hardware/sl1/tower_profiles.py:MovingProfilesTowerSL1` to get the
names of Tower profiles


# Exposure profile

- Is a set of tilt and tower parameters to manage layer peel movement.
- The values are stored in A64 for legacy reasons. Old projects are using
`expUserProfile` in `config.ini` file which defines one of the legacy exposure
profile (fast, slow or high viscosity). The new projects have all exposure
profile parameters in the `config.json` file.
- Exposure profile has the following parameters:
    - `area_fill` - former `HwConfig.limit4fast`. This parameter is the threshold
    for each layer.
    - `below_area_fill` - If the area of a particular layer is smaller than
    `area_fill`, and then `below_area_fill` parameters are used to determine
    the layer separation (tearing) procedure.
      - `delay_before_exposure_ms` - delay before exposure after previous layer
      separation
      - `delay_after_exposure_ms` - delay after exposure before layer separation
      - `tower_hop_height_nm` - the height of the tower raise
      - `tower_profile`: `layer` - tower profile used for tower raise
      - `use_tilt` - if `True` then tilt is used for layer separation.
      Otherwise, all the parameters below are ignored.
      - `tilt_down_initial_profile` - tilt profile used for an initial portion of
      tilt down move.
      - `tilt_down_offset_steps` - number of steps to move down from the
      calibrated (horizontal) position with `tilt_down_initial_profile`
      - `tilt_down_offset_delay_ms` - delay after the tilt reaches
      `tilt_down_offset_steps` position
      - `tilt_down_finish_profile` - tilt profile used for the rest of the tilt
      down move
      - `tilt_down_cycles` - number of cycles to split the rest of the tilt down
      move
      - `tilt_down_delay_ms` - the delay between tilt-down cycles
      - `tilt_up_initial_profile` - tilt profile used for an initial portion of
      tilt up move
      - `tilt_up_offset_steps` - move tilt up to calibrated (horizontal)
      position minus this offset.
      - `tilt_up_offset_delay_ms` - delay after the tilt reaches
      `tilt_up_offset_steps` position
      - `tilt_up_finish_profile` - tilt profile used for the rest of the tilt-up
      - `tilt_up_cycles` - number of cycles to split the rest of the tilt-up
      - `tilt_up_delay_ms` - the delay between tilt-up cycles
      - `moves_time_ms` - measured time of this layer separation procedure.
      This parameter will be deprecated and tilt times will be automatically
      calculated.
    - `above_area_fill` - If the area of a particular layer is
    greater than `area_fill`, then `above_area_fill` parameters are used to
    determine layer separation.
      - same parameters as `below_area_fill`

## Layer separation procedure

1. If `use_tilt` is set
   1. Set `tilt_down_initial_profile` see
   `slafw/hardware/sl1/tilt_profiles.py:MovingProfilesTiltSL1` for profile
   names.
   2. Move tilt to position `calibrated_position - tilt_down_offset_steps`.
   3. Wait `tilt_down_offset_delay_ms`.
   4. Set `tilt_down_finish_profile`.
   5. Split the rest of the tilt distance to X `tilt_down_cycles`.
   6. Wait `tilt_down_delay_ms` between `tilt_down_cycles`.
   7. Check if tilt is in the endstop ensuring no stalled steps. If a stall occurs,
   apply the tilt unstuck procedure.
2. If `tower_hop_height_nm` is greater than 0
   1. Set `tower_profile`.
   2. Raise the tower by `tower_hop_height_nm` distance.
3. If `tower_hop_height_nm` is 0
   1. Set `tower_profile` see
   `slafw/hardware/sl1/tower_profiles.py:MovingProfilesTowerSL1` for profile
   names.
   2. Raise the tower to position for the next layer.
4. If `use_tilt` is set
   1. Set `tilt_up_initial_profile`.
   2. Move tilt to position `calibrated_position - tilt_up_offset_steps`.
   3. Wait `tilt_up_offset_delay_ms`.
   4. Set `tilt_up_finish_profile`.
   5. Split the rest of the tilt distance to X `tilt_up_cycles`.
   6. Wait `tilt_up_delay_ms` between `tilt_up_cycles`.
5. If `tower_hop_height_nm` is greater than 0
   1. Lower tower to position for next layer.
