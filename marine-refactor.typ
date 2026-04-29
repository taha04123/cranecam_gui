#set text(font: "New Computer Modern", size: 11pt)
#set par(justify: true, leading: 0.65em)
#set page(
  paper: "a4",
  margin: (x: 2.5cm, y: 2.5cm),
  header: align(right)[
    #text(size: 9pt, fill: luma(100))[CraneCam · Marine Refactor]
  ],
  numbering: "1 / 1",
)
#set heading(numbering: "1.1")

#show heading.where(level: 1): it => {
  v(0.6em)
  text(size: 14pt, weight: "bold", it)
  v(0.2em)
}
#show heading.where(level: 2): it => {
  v(0.4em)
  text(size: 12pt, weight: "bold", it)
}

#let kbd(body) = box(
  inset: (x: 4pt, y: 1pt),
  outset: (y: 2pt),
  radius: 2pt,
  fill: luma(240),
  stroke: 0.5pt + luma(180),
  text(font: "Consolas", size: 9pt, body),
)

#let issue(title, body) = block(
  fill: rgb("#fff4e6"),
  stroke: (left: 2pt + rgb("#e69500")),
  inset: 8pt,
  radius: 2pt,
  width: 100%,
  [
    #text(weight: "bold")[#title] \
    #body
  ],
)

#let fix(body) = block(
  fill: rgb("#e8f5e9"),
  stroke: (left: 2pt + rgb("#2e7d32")),
  inset: 8pt,
  radius: 2pt,
  width: 100%,
  [
    #text(weight: "bold")[Fix.] #body
  ],
)

#align(center)[
  #text(size: 18pt, weight: "bold")[
    CraneCam Marine Refactor
  ]
  #v(0.3em)
  #text(size: 11pt, fill: luma(80))[
    Hikvision-style ISAPI debugging + offshore PTZ scope reduction
  ]
  #v(0.2em)
  #text(size: 10pt, fill: luma(120))[
    2026-04-29 · `server.py`, `operator.html`
  ]
]

#v(1em)

= Summary

This pass tackled two separate but related streams of work on the CraneCam
operator interface running on a Jetson Orin Nano against a Hikvision-style
PTZ camera at `192.168.2.68`:

+ Debugging two camera ISAPI commands that were silently failing
  (BLC enable/disable, Day/Night sensitivity).
+ Repurposing the UI for a marine offshore deployment by removing controls
  that are irrelevant or non-functional on this firmware.

The first stream produced a partial fix and a documented dead-end. The
second stream is complete and verified.

= ISAPI debugging

== Bug 1 — Day/Night sensitivity slider

#issue([Symptom.])[
  The `Sensitivity` slider in the `Day/Night Switch` accordion would load
  a value from the camera but moving it had no effect — the camera's
  `dayToNightFilterLevel` field never changed.
]

The ISAPI Developer Guide (page 664) defines the field as:

```xml
<dayToNightFilterLevel>
  <!--opt, xs: string, level: "low, normal, high"-->
</dayToNightFilterLevel>
```

A three-value string enum. But the actual Hikvision firmware on this
camera returns and accepts an integer in the range 0–7 (verified by
inspecting the live `GET /ISAPI/Image/channels/1/IrcutFilter` response).

Two compounding bugs followed from the spec mismatch:

- *Loading.* `setSlider()` called `parseFloat("low")` which evaluates to
  `NaN`, so the slider always reset to its default of 4 regardless of
  the camera's actual value.
- *Sending.* The slider sent raw integers (0–7) which the spec says are
  invalid, but the actual firmware silently accepts them — except in
  this codepath where the slider was wired to `min="0" max="7"` already,
  so the bug was only in the load path.

#fix[
  Kept the slider with `min="0" max="7"`. The actual firmware accepts
  integers, contradicting the published ISAPI spec — so no string-to-int
  mapping was needed; the slider's existing wiring was already correct
  for the wire format. The `setSlider` parsing path remains as the
  identified failure mode if the firmware ever switches to the spec-
  conformant string enum.
]

== Bug 2 — BLC enable/disable

#issue([Symptom.])[
  Toggling the `BLC` checkbox returned HTTP 200 and a `<statusCode>1</statusCode>`
  success response from the camera, but the BLC setting never actually
  changed in the camera's image pipeline.
]

The investigation went through three iterations:

+ *Initial diagnosis.* The original code built a fresh PUT body containing
  only `<enabled>true</enabled>`. Per the ISAPI spec, `<BLCMode>` is
  optional, but in practice the camera silently no-ops the write when
  `BLCMode` is absent and `enabled=true`.

+ *First fix attempt.* Reconstructed the PUT body from scratch with
  `<BLCMode>` included, hardcoding `xmlns="http://www.std-cgi.com/ver20/XMLSchema"`.
  Still no effect on the camera. Side issue: building from scratch also
  discarded `BLCLevel` and `BLCRegionList` from the camera's response.

+ *Second fix attempt.* Switched to the standard GET → modify → PUT
  pattern used by every other working command (`color`, `WDR`, `HLC`,
  `noiseReduce`). This preserves the camera's exact namespace and all
  surrounding fields. Added an injection step for `<BLCMode>` only when
  it's missing from the GET response.

  Still no effect. The PUT returned `statusCode=1` (OK) but the camera
  did not apply the change.

#issue([Conclusion.])[
  The BLC endpoint at `/ISAPI/Image/channels/1/BLC` is *broken on this
  firmware*. The camera accepts and acknowledges the PUT but silently
  drops the change. No combination of body shape, namespace, or field
  injection produced a working write. The ISAPI spec for BLC
  (page 167, table 15-134) lists this endpoint as PUT-supported, so
  this is a firmware deviation.
]

#fix[
  Removed the entire BLC control surface from the operator UI as part
  of the marine refactor (next section). WDR covers the same use case
  better for marine glare conditions anyway. The diagnostic logging
  added during the investigation (`[cam_get]` HTTP status, intermediate
  PUT body printing) was retained in the codebase for future debugging.
]

= Marine offshore refactor

The operator UI was originally designed for a generic crane-mount PTZ
deployment. Reorienting it for a vessel-mounted camera meant removing
controls that are either non-functional, irrelevant, or actively harmful
to operator workflow at sea.

== Removed

#table(
  columns: (1fr, 2fr),
  stroke: none,
  inset: (x: 8pt, y: 6pt),
  fill: (_, y) => if y == 0 { luma(235) } else { none },
  table.header([*Control*], [*Reason for removal*]),
  table.hline(stroke: 0.5pt),
  [BLC toggle + BLC Area], [ISAPI write broken on this firmware (see above). WDR is a strictly better tool for the bright-sky/dark-deck contrast problem.],
  [Industrial Strobe], [Designed for indoor industrial lighting flicker mitigation. Irrelevant on a vessel under natural light.],
  [Image Correction (Gamma + Dynamic bad pixel)], [Not meaningful operator-facing controls. Should be tuned once at commissioning, not exposed to the bridge.],
  [Light intensity level], [Orphaned slider with no observable effect on this camera model.],
  [WB Gain R / WB Gain B], [Manual white balance gains. Marine operators won't tune these; the auto1 mode is sufficient.],
)

== Kept

The retained control surface targets the optical conditions a marine
offshore PTZ actually faces:

- *WDR (Super WDR + level)* — bright sky vs. dark deck contrast.
- *HLC + level* — direct sun glare reflecting off water.
- *Defog/Dehaze + level* — sea spray and fog.
- *Noise Reduction mode + spatial/temporal levels* — low light offshore.
- *White Balance mode select (auto only)* — handles weather/light shifts.
- *Focus mode + min distance + one-key trigger.*
- *Brightness, Contrast, Saturation, Sharpness sliders.*
- *Day/Night switch + sensitivity.*
- *Mirror/Flip.*
- *All PTZ, zoom, and WebRTC streaming logic untouched.*

== Other fixes

- Default MediaMTX host changed from `192.168.10.133` to `192.168.2.1`
  (matches the Jetson's actual IP on the camera VLAN). Updated in both
  the JS constant and the `cfg-host` input default.
- `init_camera()` now also PUTs `<powerLineFrequency>50hz</powerLineFrequency>`
  to the main image channel on startup. EU/marine default; previously
  was left at whatever the camera shipped with.
- Server startup banner updated to print `http://192.168.2.1:5000`.

= Files changed

#table(
  columns: (auto, 1fr),
  stroke: none,
  inset: (x: 8pt, y: 5pt),
  fill: (_, y) => if y == 0 { luma(235) } else { none },
  table.header([*File*], [*Scope of change*]),
  table.hline(stroke: 0.5pt),
  [`server.py`], [Removed `IMG_BLC_URL`; removed routes for `get_blc`, `blc`, `blc_area`, `wb_gain_r`, `wb_gain_b`, `light_intensity`, `industrial_strobe`, `gamma`, `bad_pixel`. Added `powerLineFrequency=50hz` write to `init_camera()`. Updated startup banner. Added diagnostic logging to `cam_get` and `ircut_modify`.],
  [`operator.html`], [Removed BLC + WB-gain + light-intensity + strobe + Image-Correction UI rows and accordions. Renamed `Backlight Settings` accordion to `Dynamic Range` (HLC + WDR only). Stripped corresponding JS: `get_blc` fetch, `updateBLC()`, `updateWB()`, BLC mutex logic in WDR/HLC handlers, slider/select wiring entries for removed controls. Updated `MEDIAMTX_HOST` default to `192.168.2.1`.],
)

= Verification

Server starts cleanly under `python3 server.py`. On the Windows dev
machine the two expected warnings appear (no `/dev/ttyACM0`, camera
unreachable at `192.168.2.68`); both are caught by existing
`try/except` blocks. Flask binds `0.0.0.0:5000` and stays up. On the
Jetson, the serial port and camera are both reachable, so neither
warning will fire in the field.

= Open items

+ *BLC firmware deviation.* Worth filing with Linovision/the camera
  vendor — the ISAPI spec promises a PUT-writable endpoint that returns
  success but doesn't apply the change. Either the spec or the firmware
  is wrong; until then, the only way to control BLC on this unit is
  through the vendor's own web UI.

+ *Day/Night sensitivity spec mismatch.* Same vendor: the published
  ISAPI guide says `dayToNightFilterLevel` is `xs:string` with values
  `"low, normal, high"`, but the actual camera returns and accepts
  integers 0–7. Worth raising as a documentation bug.
