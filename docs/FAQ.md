# ImageSkinForLLM: FAQ

Problems seen while running the app, and how to fix them. Add a new entry each time one comes up.

## Setup shows fewer (or different) photos and recordings than before

**Why:** the app keeps everything (consent, uploads, the prepared voice and face, the accepted sample) in one app data folder. It is `.imageskin` in your home folder unless the environment variable `IMAGESKIN_HOME` names another one. If `IMAGESKIN_HOME` is set in the terminal you start the app from, for example left over from a test, the app reads that folder instead and shows only what was uploaded there. Nothing is deleted: the files are still in the other folder.

**Check:** when `imageskin serve` starts, the log has a line `App data folder` with its `path`. That is the folder the app is using.

**Fix:** clear `IMAGESKIN_HOME` to go back to the default `.imageskin` folder, or set it to the folder you were using before, then start `imageskin serve` again in the same terminal.

macOS / Linux:

```
unset IMAGESKIN_HOME
# or: export IMAGESKIN_HOME="$HOME/path/you/used/before"
imageskin serve
```

Windows 11, Command Prompt:

```
set IMAGESKIN_HOME=
rem or: set IMAGESKIN_HOME=C:\path\you\used\before
imageskin serve
```

Windows 11, PowerShell:

```
Remove-Item Env:IMAGESKIN_HOME
# or: $env:IMAGESKIN_HOME = "C:\path\you\used\before"
imageskin serve
```

These change only the current terminal. If the setting comes back in every new terminal, it was set permanently: on Windows, remove it under Settings > System > About > Advanced system settings > Environment Variables; on macOS or Linux, remove the `export IMAGESKIN_HOME=…` line from your shell profile (such as `~/.zshrc` or `~/.bashrc`).
