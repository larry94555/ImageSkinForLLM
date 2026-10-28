# The administrator's password on the hosted site

Copy `admin.example.toml` from the top of the repository here as `admin.toml` and set the password in it (roadmap R149). `compose.yaml` mounts this folder into the app read-only, and the app reads the file again whenever it changes, so there is no restart. `admin.toml` is never committed. Every step is in [docs/guides/Admin-Password-Guide.pdf](../../docs/guides/Admin-Password-Guide.pdf).
