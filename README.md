# Clipdeck

Clipdeck is a local game clipper and screen recorder for Linux. It keeps a rolling replay ready, so a keybind can save the last few seconds without opening OBS Studio. The app uses [GPU Screen Recorder](https://git.dec05eba.com/gpu-screen-recorder/about/) for capture and provides an in-app clip library, playback, and trimming.

## Supported systems

The installer detects Arch Linux and Arch derivatives such as CachyOS, plus Ubuntu and Linux Mint. Clipdeck uses GTK 4, Libadwaita, FFmpeg, MPV, and GPU Screen Recorder. Capture also depends on your GPU, driver, desktop session, and its screen-sharing portal; installing the app alone cannot guarantee that every combination works. The current checkout has been exercised on Arch; Ubuntu and Mint installation paths are implemented but still need a real-machine check.

On Wayland, install the `xdg-desktop-portal` backend for your desktop if display capture asks for one. On Ubuntu or Mint, install a compatible GPU Screen Recorder with `gsr-cli` from its [official source](https://git.dec05eba.com/gpu-screen-recorder/about/) before running Clipdeck. The installer installs distribution packages with `sudo` but does not run an upstream build script as root.

## Install

Clone the repository and run the installer as your normal user:

```bash
git clone https://github.com/Filip1x3/clipdeck.git && cd clipdeck && bash ./install.sh
```

The installer asks for `sudo` only when it needs system packages. It checks required commands and GTK libraries, makes the launch scripts executable, installs the application launcher, and adds background capture to login startup. On Ubuntu and Mint, if `gpu-screen-recorder` or `gsr-cli` is missing, install it from the official source and rerun `bash ./install.sh --no-deps`. Keep the cloned directory where it is: the launcher and keybinds refer to its `run.sh` by absolute path.

Installer options:

```bash
bash ./install.sh --check          # Check dependencies without installing anything
bash ./install.sh --no-autostart   # Install without capture at login
bash ./install.sh --no-deps        # Use dependencies already installed on the system
```

Open **Clipdeck** from your application menu after installation. You can also run `./run.sh` from the checkout.

## Using Clipdeck

- **Save a clip:** Set a keybind under **Settings → Hotkeys**, then press it while playing. Clipdeck saves the latest part of its rolling replay as an MKV file. You can choose the clip length under **Capture** and a maximum file size under **Storage**. Files larger than the limit are recompressed after capture; this may reduce visual quality, but does not shorten the clip.
- **Record a full session:** Use the recording control or its separate keybind to start and stop a recording.
- **Browse and edit:** **Home** shows recent clips; **Library** has a searchable grid. Click a clip for in-app playback. You can pause with Space, seek, change speed, use fullscreen, rename, trim to a new file, copy its path, open it in another player, or delete it after confirmation. Trimming keeps the source file.
- **Capture audio:** Select desktop audio and a microphone under **Audio**. The microphone test shows a live level and plays your test recording back. Noise suppression is available through the local PulseAudio/PipeWire WebRTC echo-cancel module.
- **Appearance:** Choose Default or Liquid Glass, background blur, and a clip-saved popup and sound. Preview controls are available in **Settings → Appearance**.
- **Background use:** Minimizing or closing the window leaves Clipdeck running in the tray. The tray menu opens the app or Library and offers Quit. Quit attempts to stop capture before exiting and reports a stop error if one occurs.

Clips default to `~/Videos`. Settings are stored in `~/.config/clipdeck/settings.json`; thumbnails are cached under `~/.cache/clipdeck/thumbnails`. Capture can start at login when the installer adds autostart. The encoded rolling replay uses RAM, so very long clip lengths can consume substantial memory. A desktop screen-capture indicator may remain visible while the rolling replay is active.

## Global keybinds

In **Settings → Hotkeys**, click **Set keybind** and press F1–F24, or use a key with Ctrl, Alt, or Super. Save the pending settings to apply the keybind. Clipdeck registers shortcuts automatically in GNOME and Cinnamon. It also integrates with a Caelestia/Hyprland user configuration when that configuration exists.

On another desktop, set these commands as custom global shortcuts in your desktop's keyboard settings:

```text
<path-to-checkout>/run.sh --save-replay
<path-to-checkout>/run.sh --toggle-recording
```

## Troubleshooting

| Problem | Check |
| --- | --- |
| No display to capture | Select a display in **Settings → Capture**. On Wayland, try **Choose with system dialog** and check your desktop's portal backend. |
| No desktop sound or microphone | Select the correct output and input devices in **Settings → Audio**. Use **Test microphone** before recording. |
| No global keybind | Check your desktop's shortcut manager. Automatic registration currently covers GNOME, Cinnamon, and the supported Caelestia/Hyprland setup. |
| Clip saving fails | Run `bash ./install.sh --check`, then check `./run.sh --status` and the capture log at `${XDG_RUNTIME_DIR:-/tmp/clipdeck-$(id -u)}/clipdeck/recorder.log`. |
| Launcher stops working after moving the folder | Run `bash ./install.sh --no-deps` again from the new location. |

## Privacy and dependencies

Clips, thumbnails, microphone tests, and settings stay on your machine. Clipdeck has no account, cloud upload, or telemetry in its runtime code. The microphone test uses a temporary local file that is removed when the test ends. Capture runs through GPU Screen Recorder; previews and trims run through local FFmpeg/MPV processes. The installer contacts your package repositories when installing dependencies.

The bundled Inter font is licensed under SIL OFL 1.1 (`assets/fonts/OFL.txt`). The bundled Lucide icons carry ISC terms, with MIT terms for Feather-derived icons (`assets/icons/LICENSE`). The notification sounds are original tones synthesized by `scripts/generate_sounds.py`; they contain no sampled audio. The application source does not yet have a project license declaration.

## Development

Run the test suite from the checkout:

```bash
python3 -m unittest discover -s tests -q
python3 scripts/generate_sounds.py --check
```

Clipdeck is a Python GTK application. `clipdeck/ui.py` contains the interface, `clipdeck/recorder.py` controls GPU Screen Recorder, `clipdeck/player.py` provides previews, and `install.py` handles system integration.
