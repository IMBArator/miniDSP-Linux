# Screenshot 2026-04-03 215312.png

Input Gain Overview.
The "Normal" button is Phase Invert

# Screenshot 2026-04-03 215419.png

Input Gate Settings.

# Screenshot 2026-04-03 215432.png

Output Compressor Settings.

# Screenshot 2026-04-03 215440.png

Output Delay Settings.

# Screenshot 2026-04-03 215453.png

Processing Chain Settings.

Top half of screenshot: Chain overview
 - Left side is input, right side is output
 - Only informational

Bottom half of screenshot: Routing Matrix
    - Columns are Outputs
    - Rows are Inputs

# Screenshot 2026-04-03 215523.png

Output Channel 1 Config Settings

Types:
- Peak
- Low Shelf
- High Shelf
- Low Pass
- High Pass
- Allpass 1
- Allpass 2

Slopes:
- BW -6
- BL -6
- BW -12
- BL -12
- LK -12
- BW -18
- BL -18
- BW -24
- BL -24
- LK -24

# Screenshot 2026-04-03 215546.png

Output Channel 2 Config Settings

# Screenshot 2026-04-03 215555.png

Output Channel 3 Config Settings

# Screenshot 2026-04-03 215603.png

Output Channel 4 Config Settings

# Screenshot 2026-04-03 215634.png

Link Selection

This is different from the Matrix: 
Clicking on the Inputs/Outputs links the settings of these together.
To be clear: It links only settings, not audio streams.
Syncing of the settings is done by the DSP, not the Config Tool. 
That means, changing settings on one of the linked channels, also changes the other changes.
When linking, the first channel in the list wins and settings are copied to the other linked channels.
Note: After linking, it is necessary to re-read the dsp configuration and update the client interface

# Screenshot 2026-04-03 215701.png

DSP Feature: Generate Noise

# Screenshot 2026-04-03 215719.png

Recall/Load Preset

DSP can store preset U01-U30.
DSP has a readonly default preset F00.

# Screenshot 2026-04-03 215734.png

Store/Save Preset

Presets names can be changed.
Max length: 15 Chars. Always length check to avoid crashing the DSP!

